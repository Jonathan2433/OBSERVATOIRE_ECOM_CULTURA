#!/usr/bin/env python3
"""Recette V6 — export filtré + revue humaine des deux thèmes.

Deux évolutions vérifiées de bout en bout (routes via TestClient, SQLite éphémère,
hors ligne) :

- **Export filtré** : `GET /api/batches/{id}/export` honore les mêmes filtres que
  la liste (niv1, sentiment, revue, rupture, churn, insatisfaction, q). Si des
  filtres sont passés, l'export ne contient QUE les lignes correspondantes
  (CSV *et* XLSX).
- **Nouveaux thèmes en revue** : `PATCH /api/results/{id}` accepte un thème /
  sous-thème hors référentiel (saisie libre), l'enregistre (`taxonomy_entries`)
  et le renvoie ensuite dans `GET /api/taxonomy` (réutilisable). Ouvert à tous les
  relecteurs (analyste inclus). Déduplication insensible à la casse ; couple
  vide refusé (400).
- **Second thème en revue** : le relecteur peut ajouter, corriger ou supprimer
  le second couple thème/sous-thème et son sentiment. ``nb_themes`` et le
  journal des corrections restent cohérents.

Usage :  python app/tests/recette_v6.py   (code de sortie 0 si aucun ÉCHEC)
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
_TMP = Path(tempfile.mkdtemp(prefix="recette_v6_"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP/'r6.db'}",
    SECRET_KEY="recette-v6", ADMIN_USERNAME="admin", ADMIN_PASSWORD="MotDePasseAdmin123!",
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


def _parse_xlsx(content: bytes) -> list[list]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


def run() -> None:
    Base.metadata.create_all(engine)
    from app.seed import seed_admin

    seed_admin()
    from app.main import app

    admin = TestClient(app)
    r = admin.post("/api/auth/login", json={"username": "admin", "password": "MotDePasseAdmin123!"})
    check("login admin", r.status_code == 200, r.status_code)
    # Relecteur analyste (gouvernance : la création de thème est ouverte à tous).
    admin.post("/api/users", json={"username": "ana6", "password": "Analyste123!", "role": "analyste"})
    ana = TestClient(app)
    ra = ana.post("/api/auth/login", json={"username": "ana6", "password": "Analyste123!"})
    check("login analyste", ra.status_code == 200, ra.status_code)

    # ============================ Export filtré =============================
    # Lot avec des verbatims « CARTE CADEAU » (dont certains churn) + du bruit.
    with SessionLocal() as db:
        b = Batch(label="export-test", status="done", seuil_revue=0.5,
                  n_total=4, n_processed=4, n_review=0, n_errors=0)
        db.add(b); db.flush()
        rows = [
            # (verbatim, niv1, niv2, sentiment, churn)
            ("Ma CARTE CADEAU est perdue", "Suivi de commande et livraison", "Colis perdu", "Négatif", True),
            ("Super livraison rapide", "Suivi de commande et livraison", "Délai non respecté", "Positif", False),
            ("CARTE CADEAU jamais reçue", "Carte cadeau physique", None, "Négatif", True),
            ("carte cadeau en minuscule", "Produit", None, "Neutre", False),
        ]
        for i, (v, n1, n2, sent, churn) in enumerate(rows):
            response = SurveyResponse(
                batch_id=b.id, source_type="MDTC-postachat",
                source_file="export_mdtc.csv",
                # Valeur volontairement sensible en clair dans la fixture :
                # ni l'API ni les deux formats d'export ne doivent la révéler.
                respondent_key=f"source-order-P9000000{i}",
                response_date=date(2026, 9, 10 + i),
                satisfaction_scale_max=4,
            )
            db.add(response); db.flush()
            db.add(Result(batch_id=b.id, survey_response_id=response.id,
                          row_index=i, source=response.source_type, verbatim_analyse=v,
                          nb_themes=1, theme1_niv1=n1, theme1_niv2=n2, theme1_sentiment=sent,
                          signal_churn=churn, revue_requise=False, confidence_globale=0.9))
        db.commit()
        bid = b.id

    # Export complet (sans filtre) -> 4 lignes de données.
    full = admin.get(f"/api/batches/{bid}/export?format=csv")
    full_rows = _parse_csv(full.content)
    check("export CSV complet -> 200", full.status_code == 200, full.status_code)
    check("export CSV complet -> 4 lignes de données", len(full_rows) - 1 == 4, len(full_rows) - 1)
    reference_col = full_rows[0].index("reference_reponse")
    references = [row[reference_col] for row in full_rows[1:]]
    check("export CSV contient une référence réponse opaque",
          all(ref.startswith("REP-") and len(ref) == 20 for ref in references), references)
    check("export CSV ne divulgue aucun identifiant source ou numéro de commande",
          "source-order" not in full.text and "P9000000" not in full.text)

    # Filtre churn + recherche texte « CARTE CADEAU » -> 2 lignes (r0, r2).
    filt = admin.get(f"/api/batches/{bid}/export?format=csv&churn=true&q=CARTE+CADEAU")
    filt_rows = _parse_csv(filt.content)
    data = filt_rows[1:]
    check("export CSV filtré (churn+q) -> 2 lignes", len(data) == 2, len(data))
    # Cohérence : ces 2 lignes doivent bien correspondre au filtre (churn ET texte).
    verb_col = filt_rows[0].index("verbatim_analysé")
    churn_col = filt_rows[0].index("signal_churn")
    ok_content = all("carte cadeau" in row[verb_col].lower() for row in data) and \
        all(str(row[churn_col]).lower() in ("true", "1") for row in data)
    check("export CSV filtré -> contenu cohérent avec le filtre", ok_content,
          [(row[verb_col], row[churn_col]) for row in data])

    # Le filtre doit s'appliquer à l'identique en XLSX.
    fx = admin.get(f"/api/batches/{bid}/export?format=xlsx&churn=true&q=CARTE+CADEAU")
    xrows = _parse_xlsx(fx.content)
    check("export XLSX filtré -> 200", fx.status_code == 200, fx.status_code)
    check("export XLSX filtré -> 2 lignes", len(xrows) - 1 == 2, len(xrows) - 1)
    xref_col = xrows[0].index("reference_reponse")
    check("export XLSX contient la même référence opaque",
          all(str(row[xref_col]).startswith("REP-") for row in xrows[1:]),
          [row[xref_col] for row in xrows[1:]])
    check("export XLSX ne divulgue aucun identifiant source ou numéro de commande",
          all("source-order" not in str(cell) and "P9000000" not in str(cell)
              for row in xrows for cell in row))

    # Filtre niv1 « contient » -> 2 lignes « Suivi de commande… ».
    fn = admin.get(f"/api/batches/{bid}/export?format=csv&niv1=Suivi")
    check("export CSV filtré niv1 -> 2 lignes", len(_parse_csv(fn.content)) - 1 == 2,
          len(_parse_csv(fn.content)) - 1)

    # La liste et l'export doivent renvoyer le même total pour un même filtre.
    lst = admin.get(f"/api/batches/{bid}/results?churn=true&q=CARTE+CADEAU").json()
    check("liste et export cohérents (même total)", lst["total"] == len(data),
          (lst["total"], len(data)))

    # Les métacaractères LIKE (%, _) doivent être littéraux (échappés), pas des jokers :
    # aucun verbatim ne contient « % » -> la recherche « % » doit renvoyer 0 ligne.
    wild = admin.get(f"/api/batches/{bid}/results?q=%25").json()  # %25 == '%'
    check("recherche '%' littérale (joker échappé) -> 0 ligne", wild["total"] == 0, wild["total"])
    wild_us = admin.get(f"/api/batches/{bid}/results?q=_").json()
    check("recherche '_' littérale (joker échappé) -> 0 ligne", wild_us["total"] == 0, wild_us["total"])

    # ==================== Nouveaux thèmes/sous-thèmes en revue ===============
    with SessionLocal() as db:
        rb = Batch(label="revue-test", status="done", seuil_revue=0.5,
                   n_total=3, n_processed=3, n_review=3, n_errors=0)
        db.add(rb); db.flush()
        rev_ids = []
        for i in range(3):
            response = SurveyResponse(
                batch_id=rb.id,
                source_type="MDTC-postrecep" if i < 2 else "Mopinion-mobile",
                source_file="revue_mdtc.xlsx" if i < 2 else "revue_mobile.xlsx",
                respondent_key=f"revue-{i}",
                response_date=date(2026, 9, 10 + i),
                satisfaction_scale_max=4 if i < 2 else 5,
            )
            db.add(response); db.flush()
            res = Result(batch_id=rb.id, row_index=i, verbatim_analyse=f"verbatim à revoir {i}",
                         source=response.source_type, survey_response_id=response.id,
                         nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                         theme1_sentiment="Neutre", revue_requise=True, reviewed=False,
                         confidence_globale=0.2)
            db.add(res); db.flush()
            rev_ids.append(res.id)
        db.commit()
        rb_id = rb.id

    scoped_review = admin.get(
        f"/api/batches/{rb_id}/review?source=MDTC-postrecep&date_from=2026-09-11&date_to=2026-09-11")
    scoped_payload = scoped_review.json() if scoped_review.status_code == 200 else {}
    scoped_item = (scoped_payload.get("items") or [{}])[0]
    check("file de revue filtrée par source et date",
          scoped_payload.get("total") == 1
          and scoped_item.get("source_file") == "revue_mdtc.xlsx",
          str(scoped_payload))
    check("file de revue expose la source et une référence opaque",
          scoped_item.get("source") == "MDTC-postrecep"
          and str(scoped_item.get("response_reference", "")).startswith("REP-")
          and "revue-1" not in str(scoped_item), str(scoped_item))

    tax0 = admin.get("/api/taxonomy").json()["themes"]
    base_niv1 = {t["niv1"] for t in tax0}
    check("taxonomie de base chargée", len(tax0) >= 20, len(tax0))
    check("thème inédit absent au départ", "Nouveau thème test" not in base_niv1)

    with SessionLocal() as db:
        entries_before = db.query(TaxonomyEntry).count()

    # (1) Analyste crée un thème ET un sous-thème entièrement nouveaux.
    p1 = ana.patch(f"/api/results/{rev_ids[0]}", json={
        "action": "correct", "theme1_niv1": "Nouveau thème test",
        "theme1_niv2": "Nouveau sous-thème", "theme1_sentiment": "Négatif"})
    check("revue : nouveau thème accepté (200)", p1.status_code == 200, (p1.status_code, p1.text))
    check("revue : résultat marqué corrigé", p1.status_code == 200 and p1.json().get("corrected") is True)

    tax1 = admin.get("/api/taxonomy").json()["themes"]
    idx1 = {t["niv1"]: t["niv2"] for t in tax1}
    check("revue : nouveau thème présent dans /api/taxonomy", "Nouveau thème test" in idx1)
    check("revue : nouveau sous-thème rattaché", "Nouveau sous-thème" in idx1.get("Nouveau thème test", []))

    # (2) Nouveau sous-thème sous un thème EXISTANT du référentiel.
    p2 = ana.patch(f"/api/results/{rev_ids[1]}", json={
        "action": "correct", "theme1_niv1": "Produit",
        "theme1_niv2": "Sous-thème inédit produit", "theme1_sentiment": "Neutre"})
    check("revue : sous-thème inédit sous thème existant (200)", p2.status_code == 200, p2.text)
    tax2 = admin.get("/api/taxonomy").json()["themes"]
    idx2 = {t["niv1"]: t["niv2"] for t in tax2}
    check("revue : sous-thème inédit rattaché à « Produit »",
          "Sous-thème inédit produit" in idx2.get("Produit", []))

    # (3) Déduplication : même couple à la casse/espaces près -> pas de doublon.
    p3 = ana.patch(f"/api/results/{rev_ids[2]}", json={
        "action": "correct", "theme1_niv1": "  nouveau thème TEST ",
        "theme1_niv2": " nouveau SOUS-thème ", "theme1_sentiment": "Négatif"})
    check("revue : couple déjà connu ré-accepté (200)", p3.status_code == 200, p3.text)
    with SessionLocal() as db:
        entries_after = db.query(TaxonomyEntry).count()
    # 2 ajouts attendus (thème+sous-thème nouveaux, puis sous-thème inédit) ; le 3e est un doublon.
    check("revue : déduplication (2 ajouts, pas 3)", entries_after - entries_before == 2,
          (entries_before, entries_after))

    # (4) Couple vide refusé.
    p4 = ana.patch(f"/api/results/{rev_ids[2]}", json={
        "action": "correct", "theme1_niv1": "Un thème", "theme1_niv2": "   "})
    check("revue : sous-thème vide refusé (400)", p4.status_code == 400, p4.status_code)

    # (5) Une correction vers un couple du référentiel de base ne crée PAS d'entrée.
    with SessionLocal() as db:
        rb2 = Batch(label="revue-base", status="done", seuil_revue=0.5,
                    n_total=1, n_processed=1, n_review=1, n_errors=0)
        db.add(rb2); db.flush()
        r5 = Result(batch_id=rb2.id, row_index=0, verbatim_analyse="verbatim base",
                    nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                    theme1_sentiment="Neutre", revue_requise=True, reviewed=False, confidence_globale=0.2)
        db.add(r5); db.flush()
        base_pair_niv1 = "Suivi de commande et livraison"
        base_pair_niv2 = "Colis perdu"
        r5_id = r5.id
        rb2_id = rb2.id
        entries_pre = db.query(TaxonomyEntry).count()
        db.commit()
    p5 = ana.patch(f"/api/results/{r5_id}", json={
        "action": "correct", "theme1_niv1": base_pair_niv1, "theme1_niv2": base_pair_niv2,
        "theme1_sentiment": "Négatif"})
    with SessionLocal() as db:
        entries_post = db.query(TaxonomyEntry).count()
    check("revue : couple du référentiel de base -> aucune entrée créée",
          p5.status_code == 200 and entries_post == entries_pre, (p5.status_code, entries_pre, entries_post))

    # (6) Couple du référentiel de base en CASSE différente -> toujours aucune entrée
    # (déduplication normalisée du référentiel de base ; régression review-finding #1).
    with SessionLocal() as db:
        rid6 = Result(batch_id=rb2_id, row_index=1, verbatim_analyse="verbatim casse",
                      nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                      theme1_sentiment="Neutre", revue_requise=True, reviewed=False, confidence_globale=0.2)
        db.add(rid6); db.flush()
        r6_id = rid6.id
        entries_pre6 = db.query(TaxonomyEntry).count()
        db.commit()
    p6 = ana.patch(f"/api/results/{r6_id}", json={
        "action": "correct", "theme1_niv1": base_pair_niv1.lower(), "theme1_niv2": base_pair_niv2.upper(),
        "theme1_sentiment": "Négatif"})
    with SessionLocal() as db:
        entries_post6 = db.query(TaxonomyEntry).count()
    check("revue : couple de base en casse différente -> aucune entrée",
          p6.status_code == 200 and entries_post6 == entries_pre6, (p6.status_code, entries_pre6, entries_post6))

    # (7) Déduplication insensible à la casse ACCENTUÉE (é/É) — régression review-finding #2.
    with SessionLocal() as db:
        rb7 = Batch(label="revue-accents", status="done", seuil_revue=0.5,
                    n_total=2, n_processed=2, n_review=2, n_errors=0)
        db.add(rb7); db.flush()
        acc_ids = []
        for i in range(2):
            ra = Result(batch_id=rb7.id, row_index=i, verbatim_analyse=f"verbatim accent {i}",
                        nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                        theme1_sentiment="Neutre", revue_requise=True, reviewed=False, confidence_globale=0.2)
            db.add(ra); db.flush()
            acc_ids.append(ra.id)
        entries_pre7 = db.query(TaxonomyEntry).count()
        db.commit()
    ana.patch(f"/api/results/{acc_ids[0]}", json={
        "action": "correct", "theme1_niv1": "Café Thé", "theme1_niv2": "Dégustation",
        "theme1_sentiment": "Positif"})
    ana.patch(f"/api/results/{acc_ids[1]}", json={
        "action": "correct", "theme1_niv1": "CAFÉ THÉ", "theme1_niv2": "DÉGUSTATION",
        "theme1_sentiment": "Positif"})
    with SessionLocal() as db:
        entries_post7 = db.query(TaxonomyEntry).count()
    check("revue : dédup insensible à la casse accentuée (1 seule entrée)",
          entries_post7 - entries_pre7 == 1, (entries_pre7, entries_post7))

    # ==================== Ajout / suppression du second thème ==============
    with SessionLocal() as db:
        rb8 = Batch(label="revue-second-theme", status="done", seuil_revue=0.5,
                    n_total=3, n_processed=3, n_review=3, n_errors=0)
        db.add(rb8); db.flush()
        mono = Result(batch_id=rb8.id, row_index=0, verbatim_analyse="mono vers bi",
                      nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                      theme1_sentiment="Neutre", revue_requise=True, reviewed=False,
                      confidence_globale=0.2)
        bi = Result(batch_id=rb8.id, row_index=1, verbatim_analyse="bi vers mono",
                    nb_themes=2, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                    theme1_sentiment="Neutre",
                    theme2_niv1="Suivi de commande et livraison", theme2_niv2="Colis perdu",
                    theme2_sentiment="Négatif", theme2_score=0.41,
                    revue_requise=True, reviewed=False, confidence_globale=0.2)
        incomplete = Result(batch_id=rb8.id, row_index=2, verbatim_analyse="second incomplet",
                            nb_themes=1, theme1_niv1="Produit", theme1_niv2="Qualité produit",
                            theme1_sentiment="Neutre", revue_requise=True, reviewed=False,
                            confidence_globale=0.2)
        db.add_all([mono, bi, incomplete]); db.flush()
        mono_id, bi_id, incomplete_id = mono.id, bi.id, incomplete.id
        db.commit()

    add_second = ana.patch(f"/api/results/{mono_id}", json={
        "action": "correct",
        "theme2_niv1": "Suivi de commande et livraison",
        "theme2_niv2": "Colis perdu",
        "theme2_sentiment": "Négatif",
    })
    added = add_second.json() if add_second.status_code == 200 else {}
    check("revue : ajout du second thème accepté", add_second.status_code == 200,
          (add_second.status_code, add_second.text))
    check("revue : second thème restitué avec son sentiment",
          added.get("theme2_niv1") == "Suivi de commande et livraison"
          and added.get("theme2_niv2") == "Colis perdu"
          and added.get("theme2_sentiment") == "Négatif", added)
    check("revue : ajout du second thème -> nb_themes=2", added.get("nb_themes") == 2,
          added.get("nb_themes"))
    with SessionLocal() as db:
        logged = {c.field for c in db.query(Correction).filter(Correction.result_id == mono_id).all()}
    check("revue : corrections du thème 2 journalisées",
          {"theme2_niv1", "theme2_niv2", "theme2_sentiment", "nb_themes"} <= logged,
          sorted(logged))

    remove_second = ana.patch(f"/api/results/{bi_id}", json={
        "action": "correct", "theme2_niv1": "", "theme2_niv2": "", "theme2_sentiment": "",
    })
    removed = remove_second.json() if remove_second.status_code == 200 else {}
    check("revue : suppression du second thème acceptée", remove_second.status_code == 200,
          (remove_second.status_code, remove_second.text))
    check("revue : suppression -> ligne mono-thème cohérente",
          removed.get("nb_themes") == 1 and not removed.get("theme2_niv1")
          and not removed.get("theme2_niv2") and not removed.get("theme2_sentiment")
          and removed.get("theme2_score") is None, removed)

    partial_second = ana.patch(f"/api/results/{incomplete_id}", json={
        "action": "correct", "theme2_niv1": "Produit", "theme2_sentiment": "Positif",
    })
    check("revue : second thème incomplet refusé (400)", partial_second.status_code == 400,
          (partial_second.status_code, partial_second.text))
    with SessionLocal() as db:
        untouched = db.get(Result, incomplete_id)
        still_pending = untouched is not None and not untouched.reviewed and not untouched.theme2_niv1
    check("revue : erreur de validation laisse le verbatim dans la file", still_pending)

    corrections = admin.get("/api/corrections/export")
    correction_rows = _parse_csv(corrections.content) if corrections.status_code == 200 else []
    correction_header = correction_rows[0] if correction_rows else []
    check("export corrections contient toute la traçabilité source/date/référence",
          {"fichier_source", "reference_reponse", "date_publication_verbatim", "date_traitement_lot"}
          <= set(correction_header), str(correction_header))
    correction_reference_col = (correction_header.index("reference_reponse")
                                if "reference_reponse" in correction_header else -1)
    correction_references = (
        [row[correction_reference_col] for row in correction_rows[1:]
         if len(row) > correction_reference_col and row[correction_reference_col]]
        if correction_reference_col >= 0 else []
    )
    check("export corrections utilise uniquement des références opaques",
          bool(correction_references)
          and all(ref.startswith("REP-") for ref in correction_references)
          and "revue-" not in corrections.text,
          str(correction_references))


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
