#!/usr/bin/env python3
"""Recette V5 — orchestration multi-moteurs, Claude (comparaison), cascade & juge.

Recette **consolidée** (lot C6) couvrant les lots C1→C5 : chaque section vérifie un
lot. Tourne **hors ligne** (Claude/LLM mockés) et **torch-free** (logique de décision
pure ; routes via TestClient). cf. docs/SPEC_V5_MULTI_MOTEUR.md.

Sections :
- C1 : refactor `llm_common` (verrou) — extraction iso-comportement des fonctions
  pures, **parité des ré-exports** `lmstudio_predictor.X is llm_common.X`, mode
  prompt « raffineur » (`build_refiner_prompt`) et `refine_cleaned_batch`
  (revalidé taxo, ordre préservé, contrat OUTPUT_COLUMNS).
- C2 : moteur Claude (comparaison/test) — client `/v1/messages` (tool use, en-têtes,
  pas de temperature, échec propre), `ClaudePredictor` (proposeur+raffineur revalidés,
  ordre/fail-fast, clé absente -> ClaudeError), `_detect_claude`, dispatch `kind=claude`,
  sync registre (jamais auto-activé) et **refus d'activation serveur** (V5-D1).
- C3 : cascade prod — `merge_cascade` (raffineur fait foi, désaccord `theme1_niv1` ->
  revue forcée), `_to_engine_pred`, migration 0006, `resolve_refiner` (LLM local seul ;
  Claude/CamemBERT/stub refusés), et `process_batch_job` en cascade de bout en bout
  (2 prédictions tracées, `chain_disagreements`, `model_label` enrichi « ▶ »).
- C4 : comparaison objective — fonctions pures (`sample_indices` reproductible, accord/
  confiance/latence/sentiment, `build_metrics` juge=None), migration 0007, `run_comparison_job`
  end-to-end (rôle `compare`, métriques), routes (RBAC admin, validations, GET/export).
- C5 : juge Claude — `build_judge_prompt` aveuglé, `judge_pairwise` (outil dédié, hors-forme->tie),
  migration 0008, `run_comparison_job` avec juge end-to-end (divergences, permutation, mapping
  A/B->moteur, win-rate), mode dégradé sans clé, endpoint verdicts paginé.

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

    # ============== C3 : orchestration cascade (production) ==================
    from types import SimpleNamespace as _NS

    import pandas as _pd
    import src.preprocessing.loader as _loader
    from common.db import Base as _Base, SessionLocal as _SL, engine as _eng
    from common.models import (
        Batch as _Batch, ENGINE_ROLE_PROPOSER, ENGINE_ROLE_REFINER, EnginePrediction,
        MODEL_KIND_CLAUDE as _KC, MODEL_KIND_LMSTUDIO as _KL, MODEL_KIND_REAL as _KR,
        MODEL_KIND_STUB as _KS, ModelVersion, Result as _Result,
    )
    from worker import tasks as _tasks
    _Base.metadata.create_all(_eng)

    # --- C3.1 merge_cascade (pur) : raffineur fait foi, désaccord -> revue forcée
    _prop = {"theme1_niv1": N1, "theme1_sentiment": "Neutre", "revue_humaine_requise": False}
    _same = {"theme1_niv1": N1, "theme1_sentiment": "Positif", "revue_humaine_requise": False}
    _diff = {"theme1_niv1": N1b, "theme1_sentiment": "Négatif", "revue_humaine_requise": False}
    o_ok, d_ok = _tasks.merge_cascade(_prop, _same)
    check("C3 : cascade accord -> pas de revue forcée + sortie raffineur prévaut",
          d_ok is False and o_ok["revue_humaine_requise"] is False and o_ok["theme1_sentiment"] == "Positif")
    o_ko, d_ko = _tasks.merge_cascade(_prop, _diff)
    check("C3 : cascade désaccord theme1_niv1 -> revue FORCÉE + flag",
          d_ko is True and o_ko["revue_humaine_requise"] is True and o_ko["theme1_niv1"] == N1b)

    # --- C3.2 _to_engine_pred : mapping vers la ligne engine_predictions ------
    _ep = _tasks._to_engine_pred(1, 2, 3, "lmstudio:x", ENGINE_ROLE_REFINER, {
        "theme1_niv1": N1, "theme1_niv2": N2, "theme1_sentiment": "Négatif",
        "confidence_globale": 0.7, "signal_churn": True}, 12.5)
    check("C3 : _to_engine_pred mappe rôle/thème/signaux/latence",
          _ep.role == ENGINE_ROLE_REFINER and _ep.theme1_niv1 == N1 and _ep.signal_churn is True
          and _ep.latency_ms == 12.5)

    # --- C3.3 Migration 0006 (chaîne + contenu) ; alembic absent du venv recette
    _mig = (ROOT / "app/api/migrations/versions/0006_cascade_engine_predictions.py").read_text(encoding="utf-8")
    check("C3 : migration 0006 chaînée sur 0005",
          'revision = "0006_cascade_engine_predictions"' in _mig and 'down_revision = "0005_audit_config"' in _mig)
    check("C3 : migration 0006 crée engine_predictions + colonnes batches",
          '"engine_predictions"' in _mig and "refiner_label" in _mig and "chain_disagreements" in _mig)
    check("C3 : table engine_predictions dans Base.metadata", "engine_predictions" in _Base.metadata.tables)

    # --- C3.4 resolve_refiner (garde-fous : LLM local seul accepté) -----------
    from app.api.routes_batches import resolve_refiner
    from fastapi import HTTPException as _HTTPExc
    with _SL() as db:
        for lbl, kind, av in [("lmstudio:r1", _KL, True), ("claude:c", _KC, True),
                              ("camembert-x", _KR, True), ("lmstudio:down", _KL, False)]:
            if db.query(ModelVersion).filter_by(label=lbl).first() is None:
                db.add(ModelVersion(kind=kind, label=lbl, available=av))
        db.commit()

        def _refused(lbl):
            try:
                resolve_refiner(db, lbl)
                return False
            except _HTTPExc as e:
                return e.status_code == 400
        check("C3 : resolve_refiner accepte un LLM local dispo",
              resolve_refiner(db, "lmstudio:r1").kind == _KL)
        check("C3 : raffineur Claude refusé (offline strict)", _refused("claude:c"))
        check("C3 : raffineur CamemBERT refusé (pas de refine_cleaned_batch)", _refused("camembert-x"))
        check("C3 : raffineur indisponible refusé", _refused("lmstudio:down"))
        check("C3 : raffineur inconnu refusé", _refused("nope:404"))

    # --- C3.5 process_batch_job : cascade de bout en bout (moteurs mockés) ----
    COL_T, COL_SA, COL_SR = _loader.COL_TEXT, _loader.COL_SATISFACTION, _loader.COL_SOURCE

    def _mk(text, niv1, rev=False):
        o = lc.empty_output(text)
        o.update({"nb_themes": 1, "theme1_niv1": niv1, "theme1_niv2": N2, "theme1_sentiment": "Neutre",
                  "theme1_score_confiance": 0.9, "confidence_globale": 0.9, "revue_humaine_requise": rev})
        return o

    class _Anon:
        def anonymize(self, raw):
            return raw, {}

    class _Clean:
        def clean(self, x):
            return x or ""

    class _FakeProposer:
        anonymizer = _Anon(); cleaner = _Clean()
        def predict_cleaned_batch(self, cleaned, sats=None):
            return [_mk(c, N1) for c in cleaned]            # propose toujours N1

    class _FakeRefiner:
        def refine_cleaned_batch(self, cleaned, sats, proposals):
            return [_mk(cleaned[0], N1), _mk(cleaned[1], N1b)]  # 0 = accord, 1 = désaccord

    _saved = (_tasks.get_active, _tasks.get_predictor, _tasks.build_worker_cfg, _loader.load_for_batch)
    try:
        _tasks.get_active = lambda db: _NS(label="stub-heuristique", kind=_KS)
        _tasks.build_worker_cfg = lambda: {"thresholds": {"revue_humaine": 0.5}}
        _loader.load_for_batch = lambda a, b, cfg: _pd.DataFrame(
            {COL_T: ["colis cassé", "site lent"], COL_SA: [2, 5], COL_SR: ["MDTC", "Mopinion"]})
        _tasks.get_predictor = lambda model, cfg: (
            _FakeRefiner() if getattr(model, "kind", None) == _KL else _FakeProposer())

        with _SL() as db:
            b = _Batch(label="cascade-test", status="pending", seuil_revue=0.5, refiner_label="lmstudio:r1")
            db.add(b); db.commit(); bid = b.id
        res = _tasks.process_batch_job(bid)
        check("C3 : process_batch_job cascade -> done", res.get("status") == "done", res)
        with _SL() as db:
            b = db.get(_Batch, bid)
            results = {r.row_index: r for r in db.query(_Result).filter_by(batch_id=bid).all()}
            eps = db.query(EnginePrediction).filter_by(batch_id=bid).all()
            check("C3 : 2 résultats + 4 engine_predictions (proposer+refiner x2)",
                  len(results) == 2 and len(eps) == 4, (len(results), len(eps)))
            check("C3 : model_label reflète la chaîne (▶)", " ▶ lmstudio:r1" in (b.model_label or ""), b.model_label)
            check("C3 : chain_disagreements = 1", b.chain_disagreements == 1, b.chain_disagreements)
            check("C3 : verbatim en désaccord -> sortie raffineur (N1b) + revue forcée",
                  results[1].theme1_niv1 == N1b and results[1].revue_requise is True)
            check("C3 : verbatim en accord -> pas de revue forcée", results[0].revue_requise is False)
            check("C3 : rôles proposer + refiner tracés",
                  sorted({e.role for e in eps}) == sorted([ENGINE_ROLE_PROPOSER, ENGINE_ROLE_REFINER]))
            check("C3 : engine_predictions rattachées au result (result_id non nul)",
                  all(e.result_id is not None for e in eps))
    finally:
        _tasks.get_active, _tasks.get_predictor, _tasks.build_worker_cfg, _loader.load_for_batch = _saved

    # ============== C4 : comparaison objective de moteurs =====================
    from worker import comparison as cmp
    from common.models import ComparisonRun, ENGINE_ROLE_COMPARE

    # --- C4.1 Fonctions pures (échantillonnage + métriques) ------------------
    check("C4 : clamp_sample_size (0->défaut, 999->borne)",
          cmp.clamp_sample_size(0) == 50 and cmp.clamp_sample_size(999) == 200)
    s1 = cmp.sample_indices(100, 10, seed=42)
    s2 = cmp.sample_indices(100, 10, seed=42)
    s3 = cmp.sample_indices(100, 10, seed=7)
    check("C4 : sample_indices reproductible (même graine -> même tirage)", s1 == s2 and s1 != s3)
    check("C4 : sample_indices borné + trié + dans [0,N)",
          len(s1) == 10 and s1 == sorted(s1) and max(s1) < 100)
    check("C4 : sample_indices couvre tout si n>=population", cmp.sample_indices(3, 10, 0) == [0, 1, 2])
    am = cmp.agreement_matrix({"A": [N1, N1, N1, N1], "B": [N1, N1b, N1, N1b]})
    check("C4 : agreement_matrix (2/4 = 0.5)", am.get("A vs B") == 0.5, am)
    cs = cmp.confidence_summary({"A": [0.8, 0.6, None, "x"]})
    check("C4 : confidence_summary (moyenne sur valides)", cs["A"]["moyenne"] == 0.7 and cs["A"]["n"] == 2, cs)
    sd = cmp.sentiment_distribution({"A": ["Négatif", "Négatif", "Positif", "?"]})
    check("C4 : sentiment_distribution", sd["A"] == {"Négatif": 2, "Neutre": 0, "Positif": 1}, sd)
    dv = cmp.divergent_indices({"A": [N1, N1, N1], "B": [N1, N1b, N1]})
    check("C4 : divergent_indices (1 divergence à l'index 1)", dv == [1], dv)
    metrics = cmp.build_metrics({"A": [N1, N1], "B": [N1, N1b]}, {"A": [0.9, 0.8], "B": [0.5, 0.4]},
                                {"A": ["Négatif", "Positif"], "B": ["Neutre", "Neutre"]},
                                {"A": 12.0, "B": 800.0}, 2)
    check("C4 : build_metrics — clés complètes + juge None (mode dégradé)",
          all(k in metrics for k in ["engines", "agreement", "confidence", "latency_ms", "sentiment", "n_divergences"])
          and metrics["judge"] is None and metrics["n_divergences"] == 1, list(metrics))

    # --- C4.2 Migration 0007 + ORM ------------------------------------------
    _m7 = (ROOT / "app/api/migrations/versions/0007_comparison_runs.py").read_text(encoding="utf-8")
    check("C4 : migration 0007 chaînée sur 0006",
          'revision = "0007_comparison_runs"' in _m7 and 'down_revision = "0006_cascade_engine_predictions"' in _m7)
    check("C4 : migration 0007 crée comparison_runs + FK comparison_run_id",
          '"comparison_runs"' in _m7 and "create_foreign_key" in _m7 and "comparison_run_id" in _m7)
    check("C4 : table comparison_runs dans Base.metadata", "comparison_runs" in _Base.metadata.tables)

    # --- C4.3 run_comparison_job de bout en bout (moteurs mockés) ------------
    class _CmpEngine:
        def __init__(self, theme_fn):
            self._t = theme_fn
        def predict_cleaned_batch(self, texts, sats=None):
            return [_mk(texts[i], self._t(i)) for i in range(len(texts))]

    with _SL() as db:
        cb = _Batch(label="cmp-src", status="done", seuil_revue=0.5)
        db.add(cb); db.flush()
        for i in range(4):
            db.add(_Result(batch_id=cb.id, row_index=i, verbatim_analyse=f"verbatim {i}", nb_themes=1))
        db.commit(); cmp_bid = cb.id
        crun = ComparisonRun(batch_id=cmp_bid, status="pending",
                             engine_labels=["stub-heuristique", "lmstudio:r1"], sample_size=10, seed=1)
        db.add(crun); db.commit(); crun_id = crun.id

    _saved2 = (_tasks.get_predictor, _tasks.build_worker_cfg)
    try:
        _tasks.build_worker_cfg = lambda: {"thresholds": {"revue_humaine": 0.5}}
        _tasks.get_predictor = lambda model, cfg: (
            _CmpEngine(lambda i: N1 if i % 2 == 0 else N1b) if getattr(model, "kind", None) == _KL
            else _CmpEngine(lambda i: N1))
        res = _tasks.run_comparison_job(crun_id)
        check("C4 : run_comparison_job -> done", res.get("status") == "done", res)
        with _SL() as db:
            run = db.get(ComparisonRun, crun_id)
            eps = db.query(EnginePrediction).filter_by(comparison_run_id=crun_id).all()
            check("C4 : engine_predictions rôle 'compare' = échantillon × moteurs (4×2=8)",
                  len(eps) == 8 and all(e.role == ENGINE_ROLE_COMPARE for e in eps), len(eps))
            check("C4 : metrics calculées (accord 0.5, 2 divergences)",
                  run.metrics and run.metrics["agreement"].get("stub-heuristique vs lmstudio:r1") == 0.5
                  and run.metrics["n_divergences"] == 2, run.metrics and run.metrics.get("agreement"))
            check("C4 : metrics — latence + confiance + sentiment par moteur",
                  set(run.metrics["latency_ms"]) == {"stub-heuristique", "lmstudio:r1"}
                  and "stub-heuristique" in run.metrics["confidence"]
                  and "lmstudio:r1" in run.metrics["sentiment"])
    finally:
        _tasks.get_predictor, _tasks.build_worker_cfg = _saved2

    # --- C4.4 Routes (RBAC + validations + GET) via TestClient ---------------
    try:
        from fastapi.testclient import TestClient
        from app.main import app as _app

        admin = TestClient(_app)
        admin.post("/api/auth/login", json={"username": "admin", "password": "MotDePasseAdmin123!"})
        # analyste pour le test RBAC
        admin.post("/api/users", json={"username": "ana5", "password": "Analyste123!", "role": "analyste"})
        ana = TestClient(_app)
        ana.post("/api/auth/login", json={"username": "ana5", "password": "Analyste123!"})

        check("C4 : lancer une comparaison interdit à l'analyste -> 403",
              ana.post(f"/api/batches/{cmp_bid}/comparisons",
                       json={"engines": ["stub-heuristique", "lmstudio:r1"], "sample_size": 10}).status_code == 403)
        # lot non terminé -> 400
        with _SL() as db:
            pend = _Batch(label="pending-cmp", status="pending", seuil_revue=0.5)
            db.add(pend); db.commit(); pend_id = pend.id
        check("C4 : comparaison sur lot non terminé -> 400",
              admin.post(f"/api/batches/{pend_id}/comparisons",
                         json={"engines": ["stub-heuristique", "lmstudio:r1"]}).status_code == 400)
        check("C4 : moteurs en double (< 2 distincts) -> 400",
              admin.post(f"/api/batches/{cmp_bid}/comparisons",
                         json={"engines": ["stub-heuristique", "stub-heuristique"]}).status_code == 400)
        check("C4 : moteur indisponible -> 400",
              admin.post(f"/api/batches/{cmp_bid}/comparisons",
                         json={"engines": ["stub-heuristique", "nope:404"]}).status_code == 400)

        # GET (consultation analyste+) : on s'appuie sur le run déjà calculé (crun_id)
        rget = ana.get(f"/api/comparisons/{crun_id}")
        check("C4 : GET /comparisons/{id} (analyste) -> 200 + metrics",
              rget.status_code == 200 and rget.json().get("metrics") is not None)
        check("C4 : GET /comparisons?batch_id liste le run",
              any(r["id"] == crun_id for r in ana.get(f"/api/comparisons?batch_id={cmp_bid}").json()))
        rv = ana.get(f"/api/comparisons/{crun_id}/verdicts")
        check("C4 : GET verdicts -> mode dégradé (total 0)", rv.status_code == 200 and rv.json().get("total") == 0)
        rexp = ana.get(f"/api/comparisons/{crun_id}/export")
        check("C4 : export CSV -> 200 + en-tête + lignes",
              rexp.status_code == 200 and "engine_label" in rexp.text and "stub-heuristique" in rexp.text)
    except ImportError as exc:
        check("C4 : (skip) routes comparaison — fastapi indisponible", True, str(exc))

    # ============== C5 : juge Claude (aveuglé + permuté) ======================
    from common.models import JudgeVerdict

    # --- C5.1 Prompt du juge AVEUGLÉ ----------------------------------------
    jp = cp.build_judge_prompt("le colis est arrivé cassé",
                               "Livraison / Retard (sentiment Négatif)", "Produit / Qualité (sentiment Négatif)")
    blob = (jp["system"] + jp["user"]).lower()
    check("C5 : prompt juge aveuglé (aucun nom de moteur)",
          not any(x in blob for x in ["lmstudio", "camembert", "claude", "stub", "qwen"]))
    check("C5 : prompt juge expose verbatim + A/B",
          "colis est arrivé cassé" in jp["user"] and "Classification A" in jp["user"] and "Classification B" in jp["user"])

    # --- C5.2 judge_pairwise (call mocké) -----------------------------------
    orig_call = cp.call_claude_messages
    try:
        cap = {}

        def _fake_judge_call(base, key, model, system, user, max_tokens, to,
                             tool_name=None, input_schema=None, tool_description=None):
            cap["tool_name"] = tool_name
            return {"winner": "B", "rationale": "B colle mieux au verbatim"}
        cp.call_claude_messages = _fake_judge_call
        v = make_claude_predictor().judge_pairwise("verbatim", "A-classif", "B-classif")
        check("C5 : judge_pairwise renvoie winner+rationale", v["winner"] == "B" and "colle" in v["rationale"])
        check("C5 : judge_pairwise utilise l'outil dédié (JUDGE_TOOL_NAME)", cap.get("tool_name") == cp.JUDGE_TOOL_NAME)
        cp.call_claude_messages = lambda *a, **k: {"winner": "???", "rationale": "x"}
        check("C5 : verdict hors-forme -> tie (neutre)",
              make_claude_predictor().judge_pairwise("v", "a", "b")["winner"] == "tie")
    finally:
        cp.call_claude_messages = orig_call

    # --- C5.3 Migration 0008 + ORM ------------------------------------------
    _m8 = (ROOT / "app/api/migrations/versions/0008_judge_verdicts.py").read_text(encoding="utf-8")
    check("C5 : migration 0008 chaînée sur 0007",
          'revision = "0008_judge_verdicts"' in _m8 and 'down_revision = "0007_comparison_runs"' in _m8)
    check("C5 : migration 0008 crée judge_verdicts", '"judge_verdicts"' in _m8 and "winner" in _m8)
    check("C5 : table judge_verdicts dans Base.metadata", "judge_verdicts" in _Base.metadata.tables)

    # --- C5.4 run_comparison_job AVEC juge (Claude mocké) -------------------
    class _FakeJudge:
        def __init__(self, cfg):
            pass
        def judge_pairwise(self, verbatim, a_c, b_c):
            # Préfère la classification contenant N1b, quel que soit le côté A/B
            # -> teste le mapping A/B -> moteur réel indépendamment de la permutation.
            if a_c.startswith(N1b):
                return {"winner": "A", "rationale": "A plus pertinent"}
            if b_c.startswith(N1b):
                return {"winner": "B", "rationale": "B plus pertinent"}
            return {"winner": "tie", "rationale": "équivalent"}

    with _SL() as db:
        jb = _Batch(label="judge-src", status="done", seuil_revue=0.5)
        db.add(jb); db.flush()
        for i in range(6):
            db.add(_Result(batch_id=jb.id, row_index=i, verbatim_analyse=f"verbatim {i}", nb_themes=1))
        db.commit(); jbid = jb.id
        jrun = ComparisonRun(batch_id=jbid, status="pending", judge_enabled=True,
                             engine_labels=["stub-heuristique", "lmstudio:r1"], sample_size=10, seed=3)
        db.add(jrun); db.commit(); jrun_id = jrun.id

    _saved3 = (_tasks.get_predictor, _tasks.build_worker_cfg, cp.ClaudePredictor)
    try:
        _tasks.build_worker_cfg = lambda: {"thresholds": {"revue_humaine": 0.5}, "claude": {"api_key_present": True}}
        _tasks.get_predictor = lambda model, cfg: (
            _CmpEngine(lambda i: N1 if i % 2 == 0 else N1b) if getattr(model, "kind", None) == _KL
            else _CmpEngine(lambda i: N1))
        cp.ClaudePredictor = _FakeJudge       # juge mocké (lazy import dans _run_judge_phase)
        res = _tasks.run_comparison_job(jrun_id)
        check("C5 : run avec juge -> done", res.get("status") == "done", res)
        with _SL() as db:
            jr = db.get(ComparisonRun, jrun_id)
            verds = db.query(JudgeVerdict).filter_by(comparison_run_id=jrun_id).all()
            jm = jr.metrics.get("judge") if jr.metrics else None
            check("C5 : metrics.judge présent (win-rate + compteurs)",
                  jm is not None and "win_rate" in jm and "n_judged" in jm, jm)
            check("C5 : nb verdicts == divergences (3 sur 6) == n_judged",
                  len(verds) == 3 and jm["n_judged"] == 3, (len(verds), jm and jm.get("n_judged")))
            check("C5 : win-rate — le moteur N1b gagne tous les duels (mapping A/B correct)",
                  jm["win_rate"].get("lmstudio:r1") == 1.0 and jm["win_rate"].get("stub-heuristique") == 0.0,
                  jm["win_rate"])
            winners = {(v.engine_a if v.winner == "a" else v.engine_b) for v in verds}
            check("C5 : tous les verdicts désignent le bon moteur réel", winners == {"lmstudio:r1"}, winners)
    finally:
        _tasks.get_predictor, _tasks.build_worker_cfg, cp.ClaudePredictor = _saved3

    # --- C5.5 Mode dégradé : juge demandé mais clé absente -------------------
    with _SL() as db:
        drun = ComparisonRun(batch_id=jbid, status="pending", judge_enabled=True,
                             engine_labels=["stub-heuristique", "lmstudio:r1"], sample_size=10, seed=4)
        db.add(drun); db.commit(); drun_id = drun.id
    _saved4 = (_tasks.get_predictor, _tasks.build_worker_cfg)
    try:
        _tasks.build_worker_cfg = lambda: {"thresholds": {"revue_humaine": 0.5}, "claude": {"api_key_present": False}}
        _tasks.get_predictor = lambda model, cfg: (
            _CmpEngine(lambda i: N1 if i % 2 == 0 else N1b) if getattr(model, "kind", None) == _KL
            else _CmpEngine(lambda i: N1))
        _tasks.run_comparison_job(drun_id)
        with _SL() as db:
            dr = db.get(ComparisonRun, drun_id)
            check("C5 : sans clé -> juge non exécuté (metrics.judge None, mode dégradé)",
                  dr.metrics is not None and dr.metrics.get("judge") is None)
            check("C5 : sans clé -> aucun verdict",
                  db.query(JudgeVerdict).filter_by(comparison_run_id=drun_id).count() == 0)
    finally:
        _tasks.get_predictor, _tasks.build_worker_cfg = _saved4

    # --- C5.6 Endpoint verdicts (paginé + verbatim) via TestClient ----------
    try:
        from fastapi.testclient import TestClient
        from app.main import app as _app2
        ana = TestClient(_app2)
        ana.post("/api/auth/login", json={"username": "admin", "password": "MotDePasseAdmin123!"})
        rv = ana.get(f"/api/comparisons/{jrun_id}/verdicts")
        body = rv.json()
        check("C5 : GET verdicts -> total 3 + items", rv.status_code == 200 and body.get("total") == 3
              and len(body.get("items", [])) == 3)
        check("C5 : verdict exposé avec verbatim + gagnant",
              all("verbatim" in it and it.get("winner") in ("a", "b", "tie") for it in body["items"]))
    except ImportError as exc:
        check("C5 : (skip) endpoint verdicts — fastapi indisponible", True, str(exc))


if __name__ == "__main__":
    run()
    fails = [r for r in _RESULTS if r[0] == "ÉCHEC"]
    width = max(len(r[1]) for r in _RESULTS)
    for status, label, detail in _RESULTS:
        line = f"  [{status:5}] {label:<{width}}"
        if status == "ÉCHEC" and detail:
            line += f"  -> {detail}"
        print(line)
    print(f"\nRecette V5 (C1+C2+C3+C4+C5) : {len(_RESULTS) - len(fails)}/{len(_RESULTS)} OK")
    sys.exit(1 if fails else 0)
