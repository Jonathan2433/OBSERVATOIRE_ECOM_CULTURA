#!/usr/bin/env python3
"""Recette V7 — correction accessible depuis Résultats (hors file de revue).

Jusqu'ici, `PATCH /api/results/{id}` n'était appelé QUE depuis la file de revue
(`revue_requise=True`), même s'il ne le vérifiait pas explicitement. Le front
(Drawer de la page Résultats) rend désormais l'action « Corriger » accessible
sur N'IMPORTE QUEL verbatim, y compris ceux que le moteur a classés avec
confiance (`revue_requise=False`, jamais passés par la file). Cette recette
fige le contrat backend dont ce nouveau point d'entrée dépend :

- corriger un résultat `revue_requise=False` fonctionne à l'identique d'une
  correction en file de revue (mêmes règles, même traçabilité) ;
- `revue_requise` n'est PAS mis à `True` par la correction : on ne fabrique pas
  une appartenance à la file qui n'a jamais existé ;
- la ligne corrigée reste absente de `GET /api/batches/{id}/review` (elle ne
  « rentre » pas dans la file) mais ressort bien `corrected=True` dans
  `GET /api/batches/{id}/results` (ce que lit la page Résultats) et dans
  `GET /api/corrections/export` (ré-entraînement) ;
- ouvert à l'analyste, pas seulement à l'admin (même règle que la revue) ;
- ajout d'un second thème et saisie libre d'un nouveau couple fonctionnent
  aussi bien en partant d'un résultat hors revue.

Usage :  python app/tests/recette_v7.py   (code de sortie 0 si aucun ÉCHEC)
"""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
for p in (str(ROOT), str(APP_DIR), str(APP_DIR / "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

# Environnement AVANT tout import (common.db lit DATABASE_URL à l'import).
_TMP = Path(tempfile.mkdtemp(prefix="recette_v7_"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP/'r7.db'}",
    SECRET_KEY="recette-v7", ADMIN_USERNAME="admin", ADMIN_PASSWORD="MotDePasseAdmin123!",
    TAXONOMY_PATH=str(ROOT / "data/raw/taxonomy_cultura_poc.json"),
    UPLOADS_DIR=str(_TMP / "uploads"), OUTPUT_DIR=str(_TMP / "output"), APP_ENV="test",
)

from fastapi.testclient import TestClient  # noqa: E402

from common.db import Base, SessionLocal, engine  # noqa: E402
from common.models import Batch, Correction, Result, SurveyResponse, TaxonomyEntry  # noqa: E402

_RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append(("OK" if ok else "ÉCHEC", label, str(detail)))


def _parse_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _make_auto_result(db, batch_id: int, row_index: int, verbatim: str, **kw) -> int:
    """Résultat « auto » : jamais passé par la file de revue."""
    response = SurveyResponse(
        batch_id=batch_id, source_type="Mopinion-ordinateur", source_file="auto.csv",
        respondent_key=f"auto-{batch_id}-{row_index}", response_date=date(2026, 9, 15),
        satisfaction_scale_max=4,
    )
    db.add(response); db.flush()
    defaults = dict(
        nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit", theme1_sentiment="Positif",
        revue_requise=False, reviewed=False, corrected=False, confidence_globale=0.93,
    )
    defaults.update(kw)
    res = Result(batch_id=batch_id, survey_response_id=response.id, row_index=row_index,
                 source=response.source_type, verbatim_analyse=verbatim, **defaults)
    db.add(res); db.flush()
    return res.id


def run() -> None:
    Base.metadata.create_all(engine)
    from app.seed import seed_admin

    seed_admin()
    from app.main import app

    admin = TestClient(app)
    r = admin.post("/api/auth/login", json={"username": "admin", "password": "MotDePasseAdmin123!"})
    check("login admin", r.status_code == 200, r.status_code)
    admin.post("/api/users", json={"username": "ana7", "password": "Analyste123!", "role": "analyste"})
    ana = TestClient(app)
    ra = ana.post("/api/auth/login", json={"username": "ana7", "password": "Analyste123!"})
    check("login analyste", ra.status_code == 200, ra.status_code)

    with SessionLocal() as db:
        batch = Batch(label="auto-corrige", status="done", seuil_revue=0.5,
                      n_total=3, n_processed=3, n_review=0, n_errors=0)
        db.add(batch); db.flush()
        auto_id = _make_auto_result(db, batch.id, 0, "verbatim classé avec confiance")
        mono_id = _make_auto_result(db, batch.id, 1, "verbatim auto mono-thème")
        freetext_id = _make_auto_result(db, batch.id, 2, "verbatim auto thème inédit")
        db.commit()
        batch_id = batch.id

    # ===== (1) Un résultat auto n'est jamais dans la file de revue =====
    queue_before = admin.get(f"/api/batches/{batch_id}/review").json()
    check("résultat auto absent de la file de revue avant correction",
          queue_before.get("total") == 0, queue_before)

    # ===== (2) Correction d'un résultat auto, par un analyste =====
    payload = {
        "action": "correct",
        "theme1_niv1": "Suivi de commande et livraison", "theme1_niv2": "Colis perdu",
        "theme1_sentiment": "Négatif",
        "signal_rupture": True, "signal_churn": False, "signal_insatisfaction": True,
    }
    p1 = ana.patch(f"/api/results/{auto_id}", json=payload)
    body1 = p1.json() if p1.status_code == 200 else {}
    check("correction d'un résultat auto acceptée (200), par un analyste",
          p1.status_code == 200, (p1.status_code, p1.text))
    check("résultat auto corrigé -> corrected=True", body1.get("corrected") is True, body1)
    check("résultat auto corrigé -> revue_requise reste False (aucune file fabriquée)",
          body1.get("revue_requise") is False, body1.get("revue_requise"))
    check("résultat auto corrigé -> nouvelles valeurs appliquées",
          body1.get("theme1_niv1") == "Suivi de commande et livraison"
          and body1.get("theme1_niv2") == "Colis perdu"
          and body1.get("theme1_sentiment") == "Négatif"
          and body1.get("signal_rupture") is True and body1.get("signal_insatisfaction") is True, body1)

    with SessionLocal() as db:
        row = db.get(Result, auto_id)
        check("résultat auto corrigé -> reviewed/reviewed_by/reviewed_at renseignés",
              row.reviewed is True and row.reviewed_by is not None and row.reviewed_at is not None,
              (row.reviewed, row.reviewed_by, row.reviewed_at))
        logged = {c.field for c in db.query(Correction).filter(Correction.result_id == auto_id).all()}
    check("correction d'un auto journalisée (thème + signaux)",
          {"theme1_niv1", "theme1_niv2", "theme1_sentiment", "signal_rupture", "signal_insatisfaction"} <= logged,
          sorted(logged))

    # ===== (3) Toujours absent de la file de revue après correction =====
    queue_after = admin.get(f"/api/batches/{batch_id}/review").json()
    check("résultat auto corrigé reste absent de la file de revue",
          queue_after.get("total") == 0, queue_after)

    # ===== (4) Visible « corrigé » dans la liste Résultats (ce que lit le Drawer) =====
    listed = admin.get(f"/api/batches/{batch_id}/results").json()
    listed_row = next((it for it in listed.get("items", []) if it["id"] == auto_id), None)
    check("résultat auto corrigé -> corrected=True dans la liste Résultats",
          listed_row is not None and listed_row.get("corrected") is True
          and listed_row.get("revue_requise") is False, listed_row)

    # ===== (5) Inclus dans l'export des corrections (ré-entraînement) =====
    export = admin.get("/api/corrections/export")
    rows = _parse_csv(export.content)
    header = rows[0] if rows else []
    verb_col = header.index("verbatim_analyse") if "verbatim_analyse" in header else -1
    exported_verbatims = [row[verb_col] for row in rows[1:]] if verb_col >= 0 else []
    check("correction hors file de revue incluse dans l'export des corrections",
          "verbatim classé avec confiance" in exported_verbatims, exported_verbatims)

    # ===== (6) Ajout d'un second thème sur un résultat auto mono-thème =====
    add_second = ana.patch(f"/api/results/{mono_id}", json={
        "action": "correct",
        "theme2_niv1": "Suivi de commande et livraison", "theme2_niv2": "Colis perdu",
        "theme2_sentiment": "Négatif",
    })
    added = add_second.json() if add_second.status_code == 200 else {}
    check("second thème ajouté à un résultat auto (200)", add_second.status_code == 200,
          (add_second.status_code, add_second.text))
    check("second thème ajouté -> nb_themes=2 et revue_requise toujours False",
          added.get("nb_themes") == 2 and added.get("revue_requise") is False, added)

    # ===== (7) Saisie libre d'un nouveau couple à partir d'un résultat auto =====
    with SessionLocal() as db:
        entries_before = db.query(TaxonomyEntry).count()
    freetext = ana.patch(f"/api/results/{freetext_id}", json={
        "action": "correct", "theme1_niv1": "Thème inédit depuis Résultats",
        "theme1_niv2": "Sous-thème inédit", "theme1_sentiment": "Neutre",
    })
    check("saisie libre d'un nouveau couple depuis un résultat auto (200)",
          freetext.status_code == 200, (freetext.status_code, freetext.text))
    tax = admin.get("/api/taxonomy").json()["themes"]
    idx = {t["niv1"]: t["niv2"] for t in tax}
    check("nouveau couple saisi depuis Résultats réutilisable ensuite (GET /api/taxonomy)",
          "Sous-thème inédit" in idx.get("Thème inédit depuis Résultats", []), idx)
    with SessionLocal() as db:
        entries_after = db.query(TaxonomyEntry).count()
    check("saisie libre depuis Résultats enregistre bien une entrée taxonomie",
          entries_after - entries_before == 1, (entries_before, entries_after))


def main() -> int:
    run()
    width = max(len(lbl) for _, lbl, _ in _RESULTS) + 2
    n_fail = 0
    for statut, label, detail in _RESULTS:
        mark = "✓" if statut == "OK" else "✗"
        line = f"[{mark}] {label.ljust(width)}"
        if statut != "OK":
            n_fail += 1
            line += f" -> {detail}"
        print(line)
    total = len(_RESULTS)
    print(f"\n{total - n_fail}/{total} OK" + ("" if n_fail == 0 else f"  ({n_fail} ÉCHEC)"))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
