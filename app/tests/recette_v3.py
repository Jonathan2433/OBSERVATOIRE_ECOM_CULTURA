#!/usr/bin/env python3
"""Recette V3 — finalisation « POC avancée ».

Vérifie les comportements ajoutés en V3 (torch-free, SQLite) :
- R1 : annulation de lot (pending/running -> canceled ; non annulable -> 409) +
       réconciliation des jobs orphelins au démarrage (running -> failed) ;
- X1 : KPI d'exploitation (admin) + RBAC ; changement de mot de passe.

La recette V1 (recette_v1.py) reste la référence de non-régression fonctionnelle.

Usage :  python app/tests/recette_v3.py   (code de sortie 0 si aucun ÉCHEC)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
for p in (str(ROOT), str(APP_DIR), str(APP_DIR / "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

_TMP = Path(tempfile.mkdtemp(prefix="recette_v3_"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP/'r3.db'}",
    SECRET_KEY="recette-v3", ADMIN_USERNAME="admin", ADMIN_PASSWORD="MotDePasseAdmin123!",
    TAXONOMY_PATH=str(ROOT / "data/raw/taxonomy_cultura_poc.json"),
    CONFIG_PATH=str(ROOT / "config/config.yaml"),
    UPLOADS_DIR=str(_TMP / "uploads"), OUTPUT_DIR=str(_TMP / "output"), APP_ENV="test",
)

_RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append(("OK" if ok else "ÉCHEC", label, str(detail)))


def section(title: str) -> None:
    _RESULTS.append(("--", title, ""))


def main() -> int:
    from fastapi.testclient import TestClient
    import common.models  # noqa: F401
    from common.db import Base, engine, SessionLocal
    Base.metadata.create_all(engine)
    from app.seed import ensure_stub_model, seed_admin
    seed_admin(); ensure_stub_model()
    from app.main import app
    from common.models import Batch

    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "admin", "password": "MotDePasseAdmin123!"})

    def mkbatch(status: str) -> int:
        with SessionLocal() as db:
            b = Batch(label=f"b-{status}", status=status, seuil_revue=0.7)
            db.add(b); db.commit(); return b.id

    # --- R1 : annulation -----------------------------------------------------
    section("R1 — Annulation de lot")
    bid = mkbatch("pending")
    r = admin.post(f"/api/batches/{bid}/cancel")
    check("Annuler un lot 'pending' -> 200 + canceled", r.status_code == 200 and r.json().get("status") == "canceled", r.status_code)
    rid = mkbatch("running")
    check("Annuler un lot 'running' -> 200", admin.post(f"/api/batches/{rid}/cancel").status_code == 200)
    did = mkbatch("done")
    check("Annuler un lot 'done' -> 409 (non annulable)", admin.post(f"/api/batches/{did}/cancel").status_code == 409)
    actions = {e["action"] for e in admin.get("/api/audit?limit=100").json()}
    check("Annulation tracée à l'audit (batch.cancel)", "batch.cancel" in actions)

    # --- R1 : réconciliation des orphelins -----------------------------------
    section("R1 — Reprise des jobs interrompus")
    orphan = mkbatch("running")
    from worker.tasks import reconcile_orphan_batches
    res = reconcile_orphan_batches()
    with SessionLocal() as db:
        st = db.get(Batch, orphan).status
    check("Lot 'running' orphelin -> 'failed' au démarrage", st == "failed" and res.get("reconciled", 0) >= 1, st)

    # --- X1 : KPI d'exploitation ---------------------------------------------
    section("X1 — Exploitation (KPI ops) & RBAC")
    o = admin.get("/api/admin/ops")
    j = o.json() if o.status_code == 200 else {}
    check("GET /api/admin/ops (admin) -> 200", o.status_code == 200)
    check("Ops : clés batches/disk/purgeable présentes",
          all(k in j for k in ("batches", "disk", "purgeable_batches", "retention_months")))
    admin.post("/api/users", json={"username": "ana", "password": "Analyste123!", "role": "analyste"})
    ana = TestClient(app)
    ana.post("/api/auth/login", json={"username": "ana", "password": "Analyste123!"})
    check("Ops interdit à l'analyste -> 403", ana.get("/api/admin/ops").status_code == 403)

    # --- X1 : changement de mot de passe -------------------------------------
    section("X1 — Changement de mot de passe")
    check("Mot de passe actuel incorrect -> 400",
          admin.post("/api/auth/password", json={"current_password": "faux", "new_password": "NouveauMdp123!"}).status_code == 400)
    check("Nouveau == ancien -> 400",
          admin.post("/api/auth/password", json={"current_password": "MotDePasseAdmin123!", "new_password": "MotDePasseAdmin123!"}).status_code == 400)
    check("Changement valide -> 200",
          admin.post("/api/auth/password", json={"current_password": "MotDePasseAdmin123!", "new_password": "NouveauMdp123!"}).status_code == 200)
    c2 = TestClient(app)
    check("Reconnexion avec le nouveau mot de passe -> 200",
          c2.post("/api/auth/login", json={"username": "admin", "password": "NouveauMdp123!"}).status_code == 200)
    check("Changement tracé à l'audit (auth.password_change)",
          "auth.password_change" in {e["action"] for e in admin.get("/api/audit?limit=100").json()})

    # --- Bilan ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  RECETTE V3 — finalisation POC avancée")
    print("=" * 70)
    fails = oks = 0
    for status_, label, detail in _RESULTS:
        if status_ == "--":
            print(f"\n▸ {label}"); continue
        icon = "✅" if status_ == "OK" else "❌"
        line = f"  {icon} {label}"
        if status_ == "ÉCHEC" and detail:
            line += f"  →  {detail}"
        print(line)
        oks += status_ == "OK"; fails += status_ == "ÉCHEC"
    print("\n" + "-" * 70)
    print(f"  Bilan V3 : {oks} OK · {fails} ÉCHEC")
    print("-" * 70)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
