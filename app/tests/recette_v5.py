#!/usr/bin/env python3
"""Recette V5 — orchestration multi-moteurs, Claude (comparaison), cascade & juge.

Recette **incrémentale** : chaque lot V5 (C1→C6) ajoute sa section ; elle sera
consolidée au lot C6. Tourne **hors ligne** (LLM mocké) et **torch-free** (logique
de décision pure). cf. docs/SPEC_V5_MULTI_MOTEUR.md.

Sections :
- C1 : refactor `llm_common` (verrou) — extraction iso-comportement des fonctions
  pures, **parité des ré-exports** `lmstudio_predictor.X is llm_common.X`, mode
  prompt « raffineur » (`build_refiner_prompt`) et `refine_cleaned_batch`
  (revalidé taxo, ordre préservé, contrat OUTPUT_COLUMNS).
- C2 : moteur Claude (comparaison/test) — client `/v1/messages` (tool use, en-têtes,
  pas de temperature, échec propre), `ClaudePredictor` (proposeur+raffineur revalidés,
  ordre/fail-fast, clé absente -> ClaudeError), `_detect_claude`, dispatch `kind=claude`,
  sync registre (jamais auto-activé) et **refus d'activation serveur** (V5-D1).

Usage :  python app/tests/recette_v5.py   (code de sortie 0 si aucun ÉCHEC)
"""
from __future__ import annotations

import inspect
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

# Environnement AVANT tout import (common.db lit DATABASE_URL à l'import ; l'API lit
# SECRET_KEY/ADMIN_*). SQLite éphémère, hors ligne. Parité avec recette_v3.
_TMP = Path(tempfile.mkdtemp(prefix="recette_v5_"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP/'r5.db'}",
    SECRET_KEY="recette-v5", ADMIN_USERNAME="admin", ADMIN_PASSWORD="MotDePasseAdmin123!",
    TAXONOMY_PATH=str(ROOT / "data/raw/taxonomy_cultura_poc.json"),
    CONFIG_PATH=str(ROOT / "config/config.yaml"),
    UPLOADS_DIR=str(_TMP / "uploads"), OUTPUT_DIR=str(_TMP / "output"), APP_ENV="test",
)
# Garde-fou recette : la clé Claude ne doit PAS fuiter de l'environnement réel.
os.environ.pop("ANTHROPIC_API_KEY", None)

from src.utils import Taxonomy  # noqa: E402
from worker import claude_predictor as cp  # noqa: E402
from worker import llm_common as lc  # noqa: E402
from worker import lmstudio_predictor as op  # noqa: E402

_RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append(("OK" if ok else "ÉCHEC", label, str(detail)))


TAXO = Taxonomy.from_json(ROOT / "data/raw/taxonomy_cultura_poc.json")
N1 = TAXO.niv1_labels[0]                        # "Suivi de commande et livraison"
N2 = TAXO.children[N1][0]                        # premier sous-thème valide
N1b = TAXO.niv1_labels[1]
N2b = TAXO.children[N1b][0]
SENT_LABELS = ["Négatif", "Neutre", "Positif"]

CFG = {
    "thresholds": {"revue_humaine": 0.50, "max_themes": 2},
    "signals": {"insatisfaction_score_max": 3},
    "lmstudio": {"fallback_theme": "Autre / Non classé", "guardrails": {
        "repli_confidence_max": 0.40,
        "invalid_json_confidence_max": 0.30,
        "review_on_sentiment_conflict": True,
    }},
}

# Symboles partagés que `lmstudio_predictor` DOIT ré-exporter (verrou anti-régression :
# des recettes/codes existants les référencent via `lmstudio_predictor.X`).
SHARED_NAMES = [
    "empty_output", "build_llm_prompt", "build_refiner_prompt", "map_llm_response",
    "OUTPUT_COLUMNS", "FALLBACK_THEME_DEFAULT", "PROMPT_VERSION_DEFAULT", "LLM_OUTPUT_SCHEMA",
]


def make_predictor(max_parallel=4, retries=0):
    """Construit un LMStudioPredictor sans I/O (attributs posés à la main)."""
    p = object.__new__(op.LMStudioPredictor)
    p.cfg, p.taxonomy, p.sentiment_labels = CFG, TAXO, SENT_LABELS
    p.base_url, p.model = "http://x:1234/v1", "m"
    p.temperature, p.timeout_s = 0.1, 5
    p.fallback_theme, p.prompt_version = "Autre / Non classé", "v1"
    p.max_parallel, p.retries = max_parallel, retries
    return p


def make_claude_predictor(max_parallel=4, retries=0, api_key="sk-test"):
    """Construit un ClaudePredictor sans I/O (attributs posés à la main)."""
    p = object.__new__(cp.ClaudePredictor)
    p.cfg, p.taxonomy, p.sentiment_labels = CFG, TAXO, SENT_LABELS
    p.base_url, p.model = "https://api.anthropic.com", "claude-opus-4-8"
    p.timeout_s, p.max_tokens = 5, 1024
    p.fallback_theme, p.prompt_version = "Autre / Non classé", "v1"
    p.max_parallel, p.retries = max_parallel, retries
    p.api_key = api_key
    return p


def run() -> None:
    # =================== C1 : refactor llm_common (verrou) ===================

    # --- C1.1 Module pur importable + contrat de sortie ----------------------
    tmpl = lc.empty_output("x")
    check("C1 : llm_common importable, empty_output conforme OUTPUT_COLUMNS",
          set(tmpl) == set(lc.OUTPUT_COLUMNS), sorted(set(lc.OUTPUT_COLUMNS) ^ set(tmpl)))
    check("C1 : empty_output -> revue forcée", tmpl["revue_humaine_requise"] is True)

    # --- C1.2 VERROU : parité des ré-exports (même objet) --------------------
    miss = [n for n in SHARED_NAMES if not hasattr(op, n)]
    check("C1 : tous les symboles partagés ré-exportés par lmstudio_predictor", not miss, miss)
    diverging = [n for n in SHARED_NAMES if getattr(op, n, object()) is not getattr(lc, n)]
    check("C1 : parité d'objet lmstudio_predictor.X is llm_common.X", not diverging, diverging)

    # --- C1.3 Proposeur inchangé (logique V4 via llm_common) -----------------
    p_prop = lc.build_llm_prompt(TAXO, "le colis est arrivé cassé", 2)
    check("C1 : prompt proposeur injecte la taxo (niv1+niv2)",
          N1 in p_prop["user"] and N2 in p_prop["user"])
    check("C1 : prompt proposeur SANS marqueur raffineur", "raffineur" not in p_prop["system"])
    raw_ok = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.9}],
              "signaux": {"rupture": False, "churn": False, "insatisfaction_forte": False}}
    PROP = lc.map_llm_response(raw_ok, "colis cassé", 2, TAXO, CFG, SENT_LABELS)
    check("C1 : map_llm_response — couple valide conservé",
          PROP["theme1_niv1"] == N1 and PROP["theme1_niv2"] == N2)
    raw_bad = {"themes": [{"niv1": N1, "niv2": "Sous-thème inexistant", "sentiment": "Positif",
                           "confidence": 0.95}], "signaux": {}}
    rb = lc.map_llm_response(raw_bad, "texte", None, TAXO, CFG, SENT_LABELS)
    check("C1 : map_llm_response — hors taxo -> repli + revue forcée",
          rb["theme1_niv1"] == "Autre / Non classé" and rb["revue_humaine_requise"] is True)

    # --- C1.4 Mode prompt RAFFINEUR -----------------------------------------
    p_ref = lc.build_refiner_prompt(TAXO, "le colis est arrivé cassé", PROP, 2)
    check("C1 : prompt raffineur injecte la taxo", N1 in p_ref["user"])
    check("C1 : prompt raffineur expose la proposition (niv1 du moteur 1)", N1 in p_ref["user"])
    check("C1 : prompt raffineur mentionne la proposition à valider/corriger",
          "Proposition du premier modèle" in p_ref["user"])
    check("C1 : prompt raffineur reprend les signaux de la proposition", "Signaux" in p_ref["user"])
    check("C1 : prompt raffineur — repli mentionné", "Autre / Non classé" in p_ref["user"])
    check("C1 : prompt raffineur — verbatim présent", "colis est arrivé cassé" in p_ref["user"])
    check("C1 : prompt raffineur — note de satisfaction injectée", "2" in p_ref["user"])
    pv = lc.build_refiner_prompt(TAXO, "x", PROP, None, "Autre / Non classé", version="v9")
    check("C1 : raffineur — version tracée + marqueur de mode",
          "[prompt v9 · raffineur]" in pv["system"], pv["system"][:30])
    check("C1 : raffineur distinct du proposeur (system différent)",
          p_ref["system"] != p_prop["system"])

    # --- C1.5 Signature conforme SPEC_V5 §4.1 (cleaned, sats, proposals) -----
    params = list(inspect.signature(op.LMStudioPredictor.refine_cleaned_batch).parameters)
    check("C1 : signature refine_cleaned_batch = (self, cleaned, satisfactions, proposals)",
          params == ["self", "cleaned", "satisfactions", "proposals"], params)

    # --- C1.6 refine_cleaned_batch : LLM mocké ------------------------------
    VALID = {"themes": [{"niv1": N1b, "niv2": N2b, "sentiment": "Neutre", "confidence": 0.8}],
             "signaux": {"rupture": False, "churn": False, "insatisfaction_forte": False}}
    orig_call = op.call_llm_chat
    try:
        captured: list[tuple[str, str]] = []

        def _capture(base, model, system, user, temp, to):
            captured.append((system, user))
            return dict(VALID)

        op.call_llm_chat = _capture
        pred = make_predictor(max_parallel=4, retries=0)
        out = pred.refine_cleaned_batch(["le colis est cassé", "   ", "site en panne"],
                                        [5, None, 5], [PROP, PROP, PROP])
        check("C1 : refine — tous les verbatims traités, ordre préservé",
              len(out) == 3 and out[1]["nb_themes"] == 0
              and out[0]["nb_themes"] >= 1 and out[2]["nb_themes"] >= 1,
              [r["nb_themes"] for r in out])
        check("C1 : refine — sortie au contrat OUTPUT_COLUMNS",
              set(out[0]) == set(op.OUTPUT_COLUMNS), sorted(set(op.OUTPUT_COLUMNS) ^ set(out[0])))
        check("C1 : refine — utilise bien le prompt RAFFINEUR",
              any("raffineur" in s for s, _ in captured))
        check("C1 : refine — la proposition du moteur 1 est transmise au LLM",
              all(N1 in u for _, u in captured))
        check("C1 : refine — sortie raffineur reprise (correction N1 -> N1b)",
              out[0]["theme1_niv1"] == N1b, out[0]["theme1_niv1"])

        # Garde-fou taxo conservé : réponse raffineur hors taxo -> repli + revue.
        op.call_llm_chat = lambda *a, **k: {"themes": [
            {"niv1": N1, "niv2": "Sous-thème bidon", "sentiment": "Positif", "confidence": 0.99}],
            "signaux": {}}
        outb = make_predictor().refine_cleaned_batch(["texte"], [None], [PROP])
        check("C1 : refine — hors taxo repasse par le repli (jamais hors taxonomie)",
              outb[0]["theme1_niv1"] == "Autre / Non classé"
              and outb[0]["revue_humaine_requise"] is True, outb[0]["theme1_niv1"])

        # Fail-fast partagé : LM Studio down -> LMStudioError propagée.
        op.call_llm_chat = lambda *a, **k: (_ for _ in ()).throw(op.LMStudioError("down"))
        raised = False
        try:
            make_predictor(max_parallel=4, retries=0).refine_cleaned_batch(
                ["a", "b", "c"], None, [PROP, PROP, PROP])
        except op.LMStudioError:
            raised = True
        check("C1 : refine — down -> LMStudioError propagée (échec propre)", raised)
    finally:
        op.call_llm_chat = orig_call

    # ============== C2 : moteur Claude (comparaison/test) ====================
    import json as _json

    # --- C2.1 Client /v1/messages : forme de requête + parsing tool use ------
    VALID_INPUT = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Neutre", "confidence": 0.8}],
                   "signaux": {"rupture": False, "churn": False, "insatisfaction_forte": False}}

    class _FakeResp:
        def __init__(self, payload): self._b = _json.dumps(payload).encode("utf-8")
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    captured: dict = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = _json.loads(req.data.decode("utf-8"))
        return _FakeResp({"content": [
            {"type": "text", "text": "ignored"},
            {"type": "tool_use", "name": cp.CLASSIFY_TOOL_NAME, "input": VALID_INPUT},
        ]})

    orig_urlopen = cp.urllib.request.urlopen
    try:
        cp.urllib.request.urlopen = _fake_urlopen
        raw = cp.call_claude_messages("https://api.anthropic.com", "sk-test", "claude-x",
                                      "sys", "usr", 1024, 5)
        check("C2 : client — bloc tool_use parsé en dict", raw == VALID_INPUT, raw)
        check("C2 : client — endpoint /v1/messages", captured["url"].endswith("/v1/messages"),
              captured["url"])
        check("C2 : client — en-têtes x-api-key + anthropic-version",
              captured["headers"].get("x-api-key") == "sk-test"
              and captured["headers"].get("anthropic-version") == cp.ANTHROPIC_VERSION,
              captured["headers"])
        check("C2 : client — tool_choice forcé sur l'outil de classification",
              captured["body"].get("tool_choice", {}).get("name") == cp.CLASSIFY_TOOL_NAME,
              captured["body"].get("tool_choice"))
        check("C2 : client — temperature NON envoyée (Opus 4.7+/Fable)",
              "temperature" not in captured["body"])

        # Pas de bloc tool_use -> {} (repli géré par map_llm_response).
        cp.urllib.request.urlopen = lambda req, timeout=None: _FakeResp({"content": [{"type": "text", "text": "x"}]})
        check("C2 : client — sans tool_use -> {}", cp.call_claude_messages(
            "https://api.anthropic.com", "sk-test", "m", "s", "u", 1024, 5) == {})

        # Clé absente -> ClaudeError (jamais d'appel réseau).
        raised = False
        try:
            cp.call_claude_messages("https://api.anthropic.com", "", "m", "s", "u", 1024, 5)
        except cp.ClaudeError:
            raised = True
        check("C2 : client — clé absente -> ClaudeError", raised)

        # HTTP error -> ClaudeError (échec propre).
        import urllib.error as _ue

        def _boom(req, timeout=None):
            raise _ue.URLError("refused")
        cp.urllib.request.urlopen = _boom
        raised = False
        try:
            cp.call_claude_messages("https://api.anthropic.com", "sk-test", "m", "s", "u", 1024, 5)
        except cp.ClaudeError:
            raised = True
        check("C2 : client — Anthropic injoignable -> ClaudeError", raised)
    finally:
        cp.urllib.request.urlopen = orig_urlopen

    # --- C2.2 ClaudePredictor (call_claude_messages mocké) -------------------
    orig_call = cp.call_claude_messages
    try:
        cap2: list = []

        def _capture(base, key, model, system, user, max_tokens, to):
            cap2.append((system, user))
            return dict(VALID_INPUT)
        cp.call_claude_messages = _capture
        pred = make_claude_predictor()
        out = pred.predict_cleaned_batch(["colis cassé", "   ", "site lent"], [2, None, 5])
        check("C2 : predict — ordre préservé + vide court-circuité",
              len(out) == 3 and out[1]["nb_themes"] == 0
              and out[0]["nb_themes"] >= 1 and out[2]["nb_themes"] >= 1, [r["nb_themes"] for r in out])
        check("C2 : predict — sortie au contrat OUTPUT_COLUMNS",
              set(out[0]) == set(lc.OUTPUT_COLUMNS))
        check("C2 : predict — couple valide revalidé par map_llm_response", out[0]["theme1_niv1"] == N1)

        # Raffineur : prompt raffineur + proposition transmise.
        PROP2 = lc.map_llm_response(
            {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.9}], "signaux": {}},
            "colis cassé", 2, TAXO, CFG, SENT_LABELS)
        cap2.clear()
        outr = make_claude_predictor().refine_cleaned_batch(["colis cassé"], [2], [PROP2])
        check("C2 : refine — contrat OUTPUT_COLUMNS", set(outr[0]) == set(lc.OUTPUT_COLUMNS))
        check("C2 : refine — prompt raffineur utilisé", any("raffineur" in s for s, _ in cap2))

        # Garde-fou taxo conservé (hors taxo -> repli + revue).
        cp.call_claude_messages = lambda *a, **k: {"themes": [
            {"niv1": "Truc inexistant", "niv2": "x", "sentiment": "Positif", "confidence": 0.99}], "signaux": {}}
        outb = make_claude_predictor().predict_cleaned_batch(["texte"], [None])
        check("C2 : predict — hors taxo -> repli + revue (jamais hors taxonomie)",
              outb[0]["theme1_niv1"] == "Autre / Non classé" and outb[0]["revue_humaine_requise"] is True)

        # Fail-fast : ClaudeError propagée.
        cp.call_claude_messages = lambda *a, **k: (_ for _ in ()).throw(cp.ClaudeError("down"))
        raised = False
        try:
            make_claude_predictor(max_parallel=4, retries=0).predict_cleaned_batch(["a", "b", "c"], None)
        except cp.ClaudeError:
            raised = True
        check("C2 : predict — down -> ClaudeError propagée (échec propre)", raised)
    finally:
        cp.call_claude_messages = orig_call

    # Clé absente -> ClaudeError dès l'appel (aucun repli silencieux).
    raised = False
    try:
        make_claude_predictor(api_key="").predict_cleaned_batch(["texte"], [None])
    except cp.ClaudeError:
        raised = True
    check("C2 : predict — sans clé -> ClaudeError (pas de repli silencieux)", raised)

    # --- C2.3 Détection _detect_claude --------------------------------------
    from worker import model_registry as mr
    check("C2 : Claude désactivé -> None", mr._detect_claude({"claude": {"enabled": False}}) is None)
    d_key = mr._detect_claude({"claude": {"enabled": True, "model": "claude-opus-4-8", "api_key_present": True}})
    check("C2 : Claude activé + clé -> available + label claude:<model>",
          d_key and d_key["available"] is True and d_key["label"] == "claude:claude-opus-4-8", d_key)
    check("C2 : Claude -> metrics comparison_only", d_key["metrics"].get("comparison_only") is True)
    d_nokey = mr._detect_claude({"claude": {"enabled": True, "api_key_present": False}})
    check("C2 : Claude activé sans clé -> indisponible", d_nokey["available"] is False)

    # --- C2.4 Dispatch get_predictor(kind=claude) ---------------------------
    from worker import classifiers as cl
    orig_cls = cp.ClaudePredictor
    try:
        cp.ClaudePredictor = lambda cfg: ("CLAUDE", cfg)
        fake_claude = type("M", (), {"kind": "claude"})()
        got = cl.get_predictor(fake_claude, {"k": 1})
        check("C2 : get_predictor(kind=claude) -> ClaudePredictor", got == ("CLAUDE", {"k": 1}), got)
    finally:
        cp.ClaudePredictor = orig_cls

    # --- C2.5 Sync registre + REFUS d'activation serveur (V5-D1) -------------
    try:
        from fastapi.testclient import TestClient
        import common.models  # noqa: F401
        from common.db import Base, SessionLocal, engine
        from common.models import MODEL_KIND_CLAUDE, ModelVersion
        from worker import model_registry as mr2

        Base.metadata.create_all(engine)
        from app.seed import ensure_stub_model, seed_admin
        seed_admin(); ensure_stub_model()
        from app.main import app

        # Sync avec Claude activé + clé présente -> entrée available, JAMAIS active.
        mr2.sync_registry({"claude": {"enabled": True, "model": "claude-opus-4-8", "api_key_present": True}})
        with SessionLocal() as db:
            row = db.query(ModelVersion).filter_by(kind=MODEL_KIND_CLAUDE).one_or_none()
            check("C2 : sync -> entrée Claude enregistrée, disponible", row is not None and row.available is True)
            check("C2 : sync -> Claude JAMAIS auto-activé", row is not None and row.is_active is False)
            claude_id = row.id if row else None

        admin = TestClient(app)
        admin.post("/api/auth/login", json={"username": "admin", "password": "MotDePasseAdmin123!"})
        models = admin.get("/api/models").json()
        check("C2 : GET /api/models inclut la ligne claude",
              any(m["kind"] == "claude" for m in models))
        r_act = admin.post(f"/api/models/{claude_id}/activate")
        check("C2 : activation Claude REFUSÉE serveur -> 400 (offline strict V5-D1)",
              r_act.status_code == 400, r_act.status_code)
        with SessionLocal() as db:
            row = db.get(ModelVersion, claude_id)
            check("C2 : Claude reste non actif après refus", row.is_active is False)

        # Re-sync désactivé -> entrée Claude neutralisée.
        mr2.sync_registry({"claude": {"enabled": False}})
        with SessionLocal() as db:
            row = db.query(ModelVersion).filter_by(kind=MODEL_KIND_CLAUDE).one()
            check("C2 : désactivation -> Claude neutralisé (available False)", row.available is False)
    except ImportError as exc:  # fastapi indisponible : section route skippée proprement
        check("C2 : (skip) refus d'activation — fastapi indisponible", True, str(exc))


if __name__ == "__main__":
    run()
    fails = [r for r in _RESULTS if r[0] == "ÉCHEC"]
    width = max(len(r[1]) for r in _RESULTS)
    for status, label, detail in _RESULTS:
        line = f"  [{status:5}] {label:<{width}}"
        if status == "ÉCHEC" and detail:
            line += f"  -> {detail}"
        print(line)
    print(f"\nRecette V5 (C1+C2) : {len(_RESULTS) - len(fails)}/{len(_RESULTS)} OK")
    sys.exit(1 if fails else 0)
