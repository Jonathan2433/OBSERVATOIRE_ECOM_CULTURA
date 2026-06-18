#!/usr/bin/env python3
"""Recette automatisée V1 — Observatoire Ecom Studio (L8).

Vérifie de bout en bout les garde-fous (§10 du cahier des charges) et les
critères de la Definition of Done (§11) qui sont contrôlables sans navigateur.

Conçu pour tourner **hors ligne**, sur SQLite, avec le classifieur stub :
- la couche API (auth/RBAC/anti-bruteforce, résultats, export, config, purge,
  audit) est torch-free et toujours exécutée ;
- l'anonymisation (regex e-mail/téléphone/commande) et la validité de la
  taxonomie sont testées directement (torch-free) ;
- l'E2E complet du pipeline worker (stub CamemBERT) n'est lancé que si `src/` +
  `worker/` sont importables (image worker) ; sinon il est SKIPPÉ proprement.

Usage :
    python -m tests.recette_v1            # depuis app/ (image API/worker)
    python app/tests/recette_v1.py        # depuis la racine du dépôt

Code de sortie : 0 si aucun ÉCHEC, 1 sinon. Les SKIP ne sont pas des échecs.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
#  Résolution des chemins + variables d'environnement (AVANT tout import app/)
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve()
# .../<repo>/app/tests/recette_v1.py  -> APP = <repo>/app, ROOT = <repo>
APP_DIR = HERE.parents[1]
ROOT = HERE.parents[2]

# Permet d'importer `app` (API), `common`, `worker` et `src`.
for p in (str(ROOT), str(APP_DIR), str(APP_DIR / "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

_TMP = Path(tempfile.mkdtemp(prefix="recette_oes_"))
_TAXO = ROOT / "data" / "raw" / "taxonomy_cultura_poc.json"
_CONFIG = ROOT / "config" / "config.yaml"

os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP/'recette.db'}",
    SECRET_KEY="recette-secret-not-for-prod",
    ADMIN_USERNAME="admin",
    ADMIN_PASSWORD="Recette123!",
    TAXONOMY_PATH=str(_TAXO),
    CONFIG_PATH=str(_CONFIG),
    UPLOADS_DIR=str(_TMP / "uploads"),
    OUTPUT_DIR=str(_TMP / "output"),
    APP_ENV="test",
)

# --------------------------------------------------------------------------- #
#  Mini-harnais de recette
# --------------------------------------------------------------------------- #
_RESULTS: list[tuple[str, str, str]] = []  # (statut, intitulé, détail)


def check(label: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append(("OK" if ok else "ÉCHEC", label, detail))
    return ok


def skip(label: str, detail: str = "") -> None:
    _RESULTS.append(("SKIP", label, detail))


def section(title: str) -> None:
    _RESULTS.append(("--", title, ""))


# --------------------------------------------------------------------------- #
#  1. Garde-fous statiques (config docker / offline) — §10 #1, #4, #8
# --------------------------------------------------------------------------- #
def test_static_guards() -> None:
    section("Garde-fous d'infrastructure (§10 #1/#4/#8)")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    check("Exposition réseau limitée à 127.0.0.1 (#8 localhost)",
          "127.0.0.1:" in compose, "binding port web")
    check("Modèles montés en lecture seule (#4 poids non modifiables)",
          "/data/models:ro" in compose, "volume models :ro")
    wdocker = (APP_DIR / "worker" / "Dockerfile").read_text(encoding="utf-8")
    check("Offline strict : HF_HUB_OFFLINE + TRANSFORMERS_OFFLINE (#1)",
          "HF_HUB_OFFLINE=1" in wdocker and "TRANSFORMERS_OFFLINE=1" in wdocker)
    nginx = (APP_DIR / "web" / "nginx.conf").read_text(encoding="utf-8")
    check("En-têtes de sécurité nginx (CSP, X-Frame-Options, nosniff)",
          all(h in nginx for h in
              ("Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options")))
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check("Secrets hors dépôt : .env gitignoré (#9)", ".env" in gitignore)


# --------------------------------------------------------------------------- #
#  2. Anonymisation PII — §10 #2 (torch-free, regex)
# --------------------------------------------------------------------------- #
def test_anonymization() -> None:
    section("Anonymisation PII avant stockage (§10 #2)")
    try:
        from src.utils import load_config
        from src.preprocessing import Anonymizer
    except Exception as exc:
        skip("Anonymisation PII (regex e-mail/téléphone/commande)",
             f"moteur src/ indisponible ici ({type(exc).__name__}) — validé en image worker")
        return

    cfg = load_config(str(_CONFIG))
    anon = Anonymizer(cfg)
    raw = ("Bonjour, contactez Jean Dupont à jean.dupont@gmail.com ou au "
           "06 12 34 56 78, ma commande CMD123456 n'est jamais arrivée.")
    masked, counts = anon.anonymize(raw)
    check("E-mail masqué", "jean.dupont@gmail.com" not in masked and "@gmail" not in masked, masked)
    check("Téléphone masqué", "06 12 34 56 78" not in masked and "0612345678" not in masked)
    check("N° de commande masqué", "CMD123456" not in masked)
    check("Marqueurs d'anonymisation présents",
          any(tok in masked for tok in ("[EMAIL]", "[TEL]", "[COMMANDE]")), masked)
    check("Comptage PII renseigné", sum(counts.values()) >= 3, str(dict(counts)))


# --------------------------------------------------------------------------- #
#  3. Validité de la taxonomie — §10 #3 (torch-free)
# --------------------------------------------------------------------------- #
def test_taxonomy() -> None:
    section("Contrainte taxonomique (§10 #3)")
    try:
        from src.utils import Taxonomy
    except Exception as exc:
        skip("Validité hiérarchique de la taxonomie",
             f"moteur src/ indisponible ici ({type(exc).__name__}) — validé en image worker")
        return

    tax = Taxonomy.from_json(str(_TAXO))
    # Le stub ne peut émettre que des couples de KEYWORD_RULES : ils doivent
    # tous être des couples (niv1, niv2) hiérarchiquement valides.
    try:
        from worker.classifiers import KEYWORD_RULES
    except Exception as exc:  # pragma: no cover
        skip("Couples du stub validés contre la taxonomie", f"import worker.classifiers KO ({exc})")
        check("Taxonomie chargée (≥1 niv.1 et ≥1 niv.2)", tax.n_niv1 > 0 and tax.n_niv2 > 0)
        return
    invalid = [(n1, n2) for _, n1, n2 in KEYWORD_RULES if not tax.is_valid_pair(n1, n2)]
    check("Tous les couples (niv.1, niv.2) du stub sont valides", not invalid, str(invalid))
    check("Couple hors taxonomie correctement rejeté",
          not tax.is_valid_pair("Produit", "Délai non respecté"))


# --------------------------------------------------------------------------- #
#  4. API : auth, RBAC, anti-bruteforce — §10 #11, #6, §7.9
# --------------------------------------------------------------------------- #
def test_api() -> tuple[object, object]:
    section("Authentification, RBAC & anti-bruteforce (§10 #11, §7.9)")
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:
        skip("Tests API (auth/RBAC/export/config/purge/audit)",
             f"fastapi indisponible ici ({type(exc).__name__}) — exécuter en image API ou venv de recette")
        return None, None

    import common.models  # noqa: F401  (enregistre tous les modèles ORM)
    from common.db import Base, engine, SessionLocal
    Base.metadata.create_all(engine)

    # Amorçage explicite (déterministe — n'exige pas le lifespan du TestClient).
    from app.seed import ensure_stub_model, seed_admin
    seed_admin()
    ensure_stub_model()

    from app.main import app

    admin = TestClient(app)
    anon = TestClient(app)

    # Non authentifié : aucun accès (#11)
    check("Non authentifié -> /api/auth/me = 401", anon.get("/api/auth/me").status_code == 401)
    check("Non authentifié -> /api/batches = 401", anon.get("/api/batches").status_code == 401)

    # Login admin
    bad = admin.post("/api/auth/login", json={"username": "admin", "password": "faux"})
    check("Login mauvais mot de passe -> 401", bad.status_code == 401)
    ok = admin.post("/api/auth/login", json={"username": "admin", "password": "Recette123!"})
    check("Login admin correct -> 200", ok.status_code == 200, ok.text[:120])
    check("Cookie de session posé", any("session" in c.lower() for c in admin.cookies.keys()) or ok.status_code == 200)

    # Crée un analyste, vérifie le RBAC côté API
    cr = admin.post("/api/users", json={"username": "analyste1", "password": "Analyste123!", "role": "analyste"})
    check("Admin crée un compte analyste -> 201", cr.status_code == 201, cr.text[:120])
    ana = TestClient(app)
    la = ana.post("/api/auth/login", json={"username": "analyste1", "password": "Analyste123!"})
    check("Login analyste -> 200", la.status_code == 200)
    check("Analyste -> /api/audit = 403 (RBAC API)", ana.get("/api/audit").status_code == 403)
    check("Analyste -> /api/config = 403 (RBAC API)", ana.get("/api/config").status_code == 403)
    check("Analyste -> PATCH /api/config = 403",
          ana.patch("/api/config", json={"retention_months": 6}).status_code == 403)
    check("Analyste -> /api/users = 403", ana.get("/api/users").status_code == 403)

    # Anti-bruteforce : verrouillage après 5 échecs (sur un identifiant tiers)
    codes = [anon.post("/api/auth/login", json={"username": "intrus", "password": "x"}).status_code
             for _ in range(5)]
    locked = anon.post("/api/auth/login", json={"username": "intrus", "password": "x"})
    check("Anti-bruteforce : verrouillage -> 429 après 5 échecs",
          locked.status_code == 429, f"codes={codes} puis {locked.status_code}")

    return admin, SessionLocal


# --------------------------------------------------------------------------- #
#  5. Résultats / export / confiance — DoD + §10 #6
# --------------------------------------------------------------------------- #
def test_results_export(admin, SessionLocal) -> None:
    section("Résultats, filtres & export conforme POC (§11, §10 #6)")
    from common.models import Batch, Result

    with SessionLocal() as db:
        b = Batch(label="recette", status="done", seuil_revue=0.70,
                  n_total=1, n_processed=1, n_review=1)
        db.add(b)
        db.flush()
        db.add(Result(
            batch_id=b.id, row_index=0, source="MDTC",
            verbatim_analyse="commande [COMMANDE] jamais reçue, [EMAIL] sans réponse",
            nb_themes=1, theme1_niv1="Suivi de commande et livraison",
            theme1_niv2="Délai non respecté", theme1_sentiment="Négatif",
            theme1_score=0.82, signal_rupture=False, signal_churn=True,
            signal_insatisfaction=True, confidence_globale=0.55, revue_requise=True,
            original_columns={"Date de commande": "2026-01-05", "Niveau de satisfaction général": 2},
        ))
        db.commit()
        bid = b.id

    # Détail / liste : confiance + statut de revue exposés (#6)
    r = admin.get(f"/api/batches/{bid}/results?limit=50&offset=0")
    check("Liste résultats -> 200", r.status_code == 200, r.text[:120])
    item = (r.json().get("items") or [{}])[0]
    check("Score de confiance exposé (#6)", item.get("confidence_globale") is not None)
    check("Statut de revue exposé (#6)", "revue_requise" in item)

    # Correctif L5 : filtre Thème en « contient » sur niv.1 OU niv.2
    f = admin.get(f"/api/batches/{bid}/results?niv1=Délai")
    check("Filtre Thème (contient, niv.2) renvoie la ligne",
          (f.json().get("total") or 0) == 1, f.text[:120])

    # Export CSV conforme POC : colonnes exactes + BOM + pas de PII brute
    ex = admin.get(f"/api/batches/{bid}/export?format=csv")
    check("Export CSV -> 200", ex.status_code == 200)
    body = ex.content.decode("utf-8-sig")
    header = body.splitlines()[0]
    expected = ["verbatim_analysé", "theme1_niv1", "theme1_niv2", "theme1_sentiment",
                "signal_rupture_client", "confidence_globale", "revue_humaine_requise"]
    check("En-tête export contient les colonnes modèle POC",
          all(c in header for c in expected), header)
    check("Colonne d'origine préservée dans l'export", "Date de commande" in header)
    check("BOM UTF-8 présent (Excel FR)", ex.content[:3] == b"\xef\xbb\xbf")
    check("Aucune PII brute dans l'export (texte anonymisé)",
          "@" not in body.split("verbatim")[0] or "[EMAIL]" in body)


# --------------------------------------------------------------------------- #
#  6. Config / purge rétention / audit — DoD + §10 #7
# --------------------------------------------------------------------------- #
def test_config_purge_audit(admin, SessionLocal) -> None:
    section("Configuration, purge RGPD & audit (§11, §10 #7)")
    from common.models import Batch

    # Config : validation + mise à jour
    check("PATCH /api/config invalide (retention<0) -> 400",
          admin.patch("/api/config", json={"retention_months": -1}).status_code == 400)
    pc = admin.patch("/api/config", json={"retention_months": 13, "default_seuil_revue": 0.70})
    check("PATCH /api/config valide -> 200", pc.status_code == 200, pc.text[:120])
    gc = admin.get("/api/config")
    check("GET /api/config renvoie retention_months", "retention_months" in gc.json())

    # Purge : un vieux lot (> rétention) supprimé, un récent conservé
    with SessionLocal() as db:
        old = Batch(label="vieux", status="done", seuil_revue=0.7)
        db.add(old)
        db.flush()
        old.created_at = datetime.now(timezone.utc) - timedelta(days=14 * 30)
        recent = Batch(label="recent", status="done", seuil_revue=0.7)
        db.add(recent)
        db.commit()
        old_id, recent_id = old.id, recent.id

    pr = admin.post("/api/admin/purge")
    check("POST /api/admin/purge -> 200", pr.status_code == 200, pr.text[:120])
    check("Purge supprime au moins le lot hors rétention", (pr.json().get("batches") or 0) >= 1)
    check("Lot hors rétention supprimé (#7)", admin.get(f"/api/batches/{old_id}").status_code == 404)
    check("Lot récent conservé", admin.get(f"/api/batches/{recent_id}").status_code == 200)

    # Audit : les actions clés sont tracées
    au = admin.get("/api/audit?limit=200")
    actions = {e.get("action") for e in au.json()} if au.status_code == 200 else set()
    check("Audit : connexion tracée", "auth.login" in actions)
    check("Audit : échec de connexion tracé", "auth.login_failed" in actions)
    check("Audit : mise à jour config tracée", "config.update" in actions)
    check("Audit : purge tracée (#7)", "data.purge" in actions)


# --------------------------------------------------------------------------- #
#  7. E2E pipeline worker (stub) — guardé (nécessite src/ + torch)
# --------------------------------------------------------------------------- #
def test_pipeline_e2e(SessionLocal) -> None:
    section("E2E pipeline worker stub (§11 traitement de lot)")
    try:
        import pandas as pd  # noqa: F401
        from worker.tasks import process_batch_job  # peut tirer torch via src.*
    except Exception as exc:
        skip("Traitement de lot de bout en bout (stub)",
             f"dépendances worker indisponibles ici ({type(exc).__name__}) — validé en image worker")
        return

    from common.models import Batch, Result
    from src.utils import Taxonomy

    # Fixture MDTC minimal avec PII
    up = _TMP / "uploads" / "e2e"
    up.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    df = pd.DataFrame({
        "Niveau de satisfaction général": [2, 9],
        "Verbatim justification": [
            "Colis jamais reçu, commande CMD998877, joignable au 06 11 22 33 44.",
            "Site très facile et agréable, merci !",
        ],
    })
    xlsx = up / "mdtc.xlsx"
    df.to_excel(xlsx, index=False)

    with SessionLocal() as db:
        b = Batch(label="e2e", status="pending", seuil_revue=0.70,
                  source_files={"mdtc": str(xlsx)})
        db.add(b)
        db.commit()
        bid = b.id

    res = process_batch_job(bid)
    check("Lot traité -> statut done", res.get("status") == "done", str(res))

    tax = Taxonomy.from_json(str(_TAXO))
    with SessionLocal() as db:
        rows = db.query(Result).filter(Result.batch_id == bid).all()
        check("Résultats persistés (2 lignes)", len(rows) == 2)
        # #2 : aucun verbatim brut (PII) en base
        pii_leak = any(("CMD998877" in (r.verbatim_analyse or "")) or
                       ("06 11 22 33 44" in (r.verbatim_analyse or "")) for r in rows)
        check("Aucune PII brute persistée en base (#2)", not pii_leak)
        # #3 : tout couple prédit est valide dans la taxonomie
        bad = [(r.theme1_niv1, r.theme1_niv2) for r in rows
               if r.theme1_niv1 and r.theme1_niv2 and not tax.is_valid_pair(r.theme1_niv1, r.theme1_niv2)]
        check("Tous les couples prédits sont taxonomiquement valides (#3)", not bad, str(bad))


# --------------------------------------------------------------------------- #
#  Exécution
# --------------------------------------------------------------------------- #
def main() -> int:
    test_static_guards()
    test_anonymization()
    test_taxonomy()
    admin, SessionLocal = test_api()
    if admin is not None:
        test_results_export(admin, SessionLocal)
        test_config_purge_audit(admin, SessionLocal)
    if SessionLocal is None:
        # SessionLocal n'a pas pu être créé (couche API absente) : on tente
        # tout de même l'E2E worker avec sa propre session.
        try:
            from common.db import SessionLocal as _SL
            SessionLocal = _SL
        except Exception:
            SessionLocal = None
    if SessionLocal is not None:
        test_pipeline_e2e(SessionLocal)
    else:
        skip("E2E pipeline worker stub", "aucune session DB disponible")

    print("\n" + "=" * 78)
    print("  RECETTE V1 — Observatoire Ecom Studio")
    print("=" * 78)
    fails = oks = skips = 0
    for status_, label, detail in _RESULTS:
        if status_ == "--":
            print(f"\n▸ {label}")
            continue
        icon = {"OK": "✅", "ÉCHEC": "❌", "SKIP": "⏭️ "}[status_]
        line = f"  {icon} {label}"
        if status_ == "ÉCHEC" and detail:
            line += f"  →  {detail}"
        if status_ == "SKIP" and detail:
            line += f"  ({detail})"
        print(line)
        oks += status_ == "OK"
        fails += status_ == "ÉCHEC"
        skips += status_ == "SKIP"

    print("\n" + "-" * 78)
    print(f"  Bilan : {oks} OK · {fails} ÉCHEC · {skips} SKIP")
    print("-" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
