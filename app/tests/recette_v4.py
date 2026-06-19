#!/usr/bin/env python3
"""Recette V4 — moteur LM Studio (LLM local).

Vérifie le moteur LM Studio de bout en bout SANS service réel (HTTP mocké) et SANS
torch (fonctions pures de mapping/validation). Couvre les lots O1 à O4.

- O1 : gabarit de sortie (OUTPUT_COLUMNS), prompt (taxo injectée), mapping
  couple valide / repli, signaux, verbatim vide, client HTTP (parse/erreur).
- O2 : matching tolérant (casse/accents), 2 plafonds de confiance, dé-doublonnage,
  conflit de sentiment, prompt versionné.
- O3 : détection LM Studio (`/v1/models`), `available` dynamique, synchro registre.
- O4 : pool borné (ordre préservé), retries, fail-fast (échec propre si down).

Usage :  python app/tests/recette_v4.py   (code de sortie 0 si aucun ÉCHEC)
"""
from __future__ import annotations

import os
import sys
import tempfile
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
for p in (str(ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Base SQLite éphémère AVANT tout import de common.db (lit DATABASE_URL à l'import).
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(tempfile.mkdtemp(prefix='recette_v4_'))/'r4.db'}")

from src.utils import Taxonomy  # noqa: E402
from worker import lmstudio_predictor as op  # noqa: E402

_RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append(("OK" if ok else "ÉCHEC", label, str(detail)))


TAXO = Taxonomy.from_json(ROOT / "data/raw/taxonomy_cultura_poc.json")
N1 = TAXO.niv1_labels[0]                       # "Suivi de commande et livraison"
N2 = TAXO.children[N1][0]                       # premier sous-thème valide
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


def run() -> None:
    # --- 1. Gabarit de sortie == contrat OUTPUT_COLUMNS ----------------------
    tmpl = op.empty_output("x")
    check("empty_output : clés conformes au contrat", set(tmpl) == set(op.OUTPUT_COLUMNS),
          sorted(set(op.OUTPUT_COLUMNS) ^ set(tmpl)))
    check("empty_output : revue forcée", tmpl["revue_humaine_requise"] is True)

    # --- 2. Prompt -----------------------------------------------------------
    p = op.build_llm_prompt(TAXO, "le colis est arrivé cassé", 2)
    check("prompt : taxonomie injectée (niv1)", N1 in p["user"])
    check("prompt : sous-thème injecté (niv2)", N2 in p["user"])
    check("prompt : repli mentionné", "Autre / Non classé" in p["user"])
    check("prompt : verbatim présent", "colis est arrivé cassé" in p["user"])
    check("prompt : note de satisfaction injectée", "2" in p["user"])

    # --- 3. Mapping : couple valide accepté ----------------------------------
    raw_ok = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.9}],
              "signaux": {"rupture": False, "churn": False, "insatisfaction_forte": False}}
    r = op.map_llm_response(raw_ok, "colis cassé", 2, TAXO, CFG, SENT_LABELS)
    check("map : niv1 conservé", r["theme1_niv1"] == N1, r["theme1_niv1"])
    check("map : niv2 conservé", r["theme1_niv2"] == N2, r["theme1_niv2"])
    check("map : confiance reprise", r["confidence_globale"] == 0.9, r["confidence_globale"])
    check("map : pas de revue (conf 0.9 > seuil)", r["revue_humaine_requise"] is False)
    # insatisfaction métier : note<=3 ET Négatif -> True
    check("map : insatisfaction métier déclenchée", r["signal_insatisfaction_forte"] is True)

    # --- 4. Mapping : couple invalide -> repli + revue forcée ----------------
    raw_bad = {"themes": [{"niv1": N1, "niv2": "Sous-thème inexistant", "sentiment": "Positif",
                           "confidence": 0.95}], "signaux": {}}
    rb = op.map_llm_response(raw_bad, "texte", None, TAXO, CFG, SENT_LABELS)
    check("map : couple invalide -> sentinelle de repli", rb["theme1_niv1"] == "Autre / Non classé",
          rb["theme1_niv1"])
    check("map : repli -> revue forcée", rb["revue_humaine_requise"] is True)
    check("map : repli -> confiance plafonnée <= 0.40", rb["confidence_globale"] <= 0.40,
          rb["confidence_globale"])

    # --- 5. Mapping : niv1 totalement hors taxonomie -------------------------
    raw_niv1 = {"themes": [{"niv1": "Marketing lunaire", "niv2": "x", "sentiment": "Neutre",
                            "confidence": 0.8}], "signaux": {}}
    rn = op.map_llm_response(raw_niv1, "texte", None, TAXO, CFG, SENT_LABELS)
    check("map : niv1 inconnu -> repli", rn["theme1_niv1"] == "Autre / Non classé", rn["theme1_niv1"])

    # --- 6. Mapping : sentiment invalide -> Neutre + revue -------------------
    raw_sent = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Enthousiaste", "confidence": 0.9}],
                "signaux": {}}
    rs = op.map_llm_response(raw_sent, "texte", None, TAXO, CFG, SENT_LABELS)
    check("map : sentiment invalide -> Neutre", rs["theme1_sentiment"] == "Neutre", rs["theme1_sentiment"])
    check("map : sentiment invalide -> revue forcée", rs["revue_humaine_requise"] is True)

    # --- 7. Mapping : réponse vide / hors-forme -> repli + revue -------------
    re = op.map_llm_response({}, "texte", None, TAXO, CFG, SENT_LABELS)
    check("map : réponse vide -> repli", re["theme1_niv1"] == "Autre / Non classé")
    check("map : réponse vide -> revue", re["revue_humaine_requise"] is True)

    # --- 8. Mapping : verbatim vide -> revue, 0 thème ------------------------
    rv = op.map_llm_response(raw_ok, "   ", None, TAXO, CFG, SENT_LABELS)
    check("map : verbatim vide -> 0 thème", rv["nb_themes"] == 0)
    check("map : verbatim vide -> revue", rv["revue_humaine_requise"] is True)

    # --- 9. Signaux : rupture => churn ---------------------------------------
    raw_rup = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.8}],
               "signaux": {"rupture": True, "churn": False, "insatisfaction_forte": False}}
    rr = op.map_llm_response(raw_rup, "je pars chez la concurrence", 5, TAXO, CFG, SENT_LABELS)
    check("map : rupture force churn", rr["signal_churn"] is True and rr["signal_rupture_client"] is True)

    # ====================== O2 : durcissement ===============================
    N1b = TAXO.niv1_labels[1]
    N2b = TAXO.children[N1b][0]

    # --- O2.1 Matching tolérant niv1/niv2 (casse + accents) -> canonique -----
    import unicodedata as _ud
    def _deaccent_upper(s): return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    raw_case = {"themes": [{"niv1": _deaccent_upper(N1), "niv2": _deaccent_upper(N2),
                            "sentiment": "Négatif", "confidence": 0.9}], "signaux": {}}
    rc = op.map_llm_response(raw_case, "texte", None, TAXO, CFG, SENT_LABELS)
    check("O2 : niv1 mal capitalisé -> libellé canonique", rc["theme1_niv1"] == N1, rc["theme1_niv1"])
    check("O2 : niv2 sans accent -> libellé canonique", rc["theme1_niv2"] == N2, rc["theme1_niv2"])
    check("O2 : couple récupéré -> pas de repli", rc["theme1_niv1"] != "Autre / Non classé")

    # --- O2.2 Sentiment tolérant ("NEGATIF" -> "Négatif") --------------------
    raw_sc = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "NEGATIF", "confidence": 0.9}],
              "signaux": {}}
    rsc = op.map_llm_response(raw_sc, "texte", None, TAXO, CFG, SENT_LABELS)
    check("O2 : sentiment tolérant -> canonique", rsc["theme1_sentiment"] == "Négatif",
          rsc["theme1_sentiment"])
    check("O2 : sentiment reconnu -> pas de revue forcée", rsc["revue_humaine_requise"] is False)

    # --- O2.3 Plafond JSON hors-forme (0.30) distinct du repli (0.40) --------
    rj = op.map_llm_response({}, "texte", None, TAXO, CFG, SENT_LABELS)
    check("O2 : JSON hors-forme -> confiance <= 0.30", rj["confidence_globale"] <= 0.30,
          rj["confidence_globale"])

    # --- O2.4 Dé-doublonnage de thèmes identiques ----------------------------
    raw_dup = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.8},
                          {"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.7}],
               "signaux": {}}
    rd = op.map_llm_response(raw_dup, "texte", None, TAXO, CFG, SENT_LABELS)
    check("O2 : doublon de thème fusionné -> 1 thème", rd["nb_themes"] == 1, rd["nb_themes"])

    # --- O2.5 Désaccord de sentiment (dont Négatif) -> revue forcée ----------
    raw_conf = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Négatif", "confidence": 0.95},
                           {"niv1": N1b, "niv2": N2b, "sentiment": "Positif", "confidence": 0.95}],
                "signaux": {}}
    rcf = op.map_llm_response(raw_conf, "texte", None, TAXO, CFG, SENT_LABELS)
    check("O2 : 2 thèmes, sentiments divergents -> revue forcée", rcf["revue_humaine_requise"] is True)
    check("O2 : 2 thèmes distincts conservés", rcf["nb_themes"] == 2, rcf["nb_themes"])

    # --- O2.6 Prompt versionné ----------------------------------------------
    pv = op.build_llm_prompt(TAXO, "x", None, "Autre / Non classé", version="v9")
    check("O2 : version de prompt tracée", "[prompt v9]" in pv["system"], pv["system"][:20])

    # --- 10. Client HTTP : parse OK (urlopen mocké) --------------------------
    import json as _json

    class _FakeResp:
        def __init__(self, payload): self._b = _json.dumps(payload).encode("utf-8")
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    content = _json.dumps({"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Neutre", "confidence": 0.7}],
                           "signaux": {"rupture": False, "churn": False, "insatisfaction_forte": False}})
    orig_urlopen = op.urllib.request.urlopen
    try:
        op.urllib.request.urlopen = lambda req, timeout=None: _FakeResp({"choices": [{"message": {"content": content}}]})
        parsed = op.call_llm_chat("http://x:1234/v1", "m", "sys", "usr", 0.1, 5)
        check("client : parse JSON OK (choices OpenAI)", isinstance(parsed, dict) and parsed.get("themes"), parsed)

        # JSON malformé dans content -> {} (repli géré par le mapping)
        op.urllib.request.urlopen = lambda req, timeout=None: _FakeResp({"choices": [{"message": {"content": "pas du json"}}]})
        bad = op.call_llm_chat("http://x:1234/v1", "m", "s", "u", 0.1, 5)
        check("client : content non-JSON -> {}", bad == {}, bad)

        # Service injoignable -> LMStudioError (échec propre)
        def _boom(req, timeout=None):
            raise urllib.error.URLError("connection refused")
        op.urllib.request.urlopen = _boom
        raised = False
        try:
            op.call_llm_chat("http://x:1234/v1", "m", "s", "u", 0.1, 5)
        except op.LMStudioError:
            raised = True
        check("client : LM Studio down -> LMStudioError", raised)
    finally:
        op.urllib.request.urlopen = orig_urlopen

    # ====================== O3 : registre & détection =======================
    from common.db import Base, SessionLocal, engine
    from common.models import MODEL_KIND_LMSTUDIO, ModelVersion
    from worker import model_registry as mr

    orig_list = op.list_llm_models
    try:
        # 1. Moteur désactivé -> aucune entrée détectée.
        check("O3 : LM Studio désactivé -> None", mr._detect_lmstudio({"lmstudio": {"enabled": False}}) is None)

        cfg_lms = {"lmstudio": {"enabled": True, "model": "mon-modele", "base_url": "http://x:1234/v1"}}

        # 2. Joignable + modèle présent -> available True.
        op.list_llm_models = lambda *a, **k: ["mon-modele", "autre-modele"]
        d = mr._detect_lmstudio(cfg_lms)
        check("O3 : modèle présent -> available", d and d["available"] is True, d)
        check("O3 : label = lmstudio:<model>", d["label"] == "lmstudio:mon-modele", d["label"])

        # 3. Joignable mais modèle absent -> available False + motif.
        op.list_llm_models = lambda *a, **k: ["autre-modele"]
        d2 = mr._detect_lmstudio(cfg_lms)
        check("O3 : modèle absent -> indisponible", d2["available"] is False)
        check("O3 : metrics reachable=True, present=False",
              d2["metrics"]["reachable"] is True and d2["metrics"]["model_present"] is False, d2["metrics"])

        # 4. Injoignable -> available False, reachable False (échec propre, pas d'exception).
        def _down(*a, **k):
            raise op.LMStudioError("refused")
        op.list_llm_models = _down
        d3 = mr._detect_lmstudio(cfg_lms)
        check("O3 : LM Studio injoignable -> indisponible", d3["available"] is False)
        check("O3 : metrics reachable=False", d3["metrics"]["reachable"] is False)

        # 5. Synchro complète en base : stub + entrée lmstudio (kind=lmstudio, available).
        Base.metadata.create_all(bind=engine)
        op.list_llm_models = lambda *a, **k: ["mon-modele"]
        mr.sync_registry(cfg_lms)
        with SessionLocal() as db:
            lms_row = db.query(ModelVersion).filter_by(kind=MODEL_KIND_LMSTUDIO).one_or_none()
            check("O3 : entrée LM Studio enregistrée", lms_row is not None and lms_row.available is True)
            check("O3 : stub reste actif par défaut (pas d'auto-activation LM Studio)",
                  db.query(ModelVersion).filter_by(is_active=True).count() == 1
                  and lms_row.is_active is False)

        # 6. Re-synchro moteur désactivé -> l'entrée LM Studio devient indisponible.
        mr.sync_registry({"lmstudio": {"enabled": False}})
        with SessionLocal() as db:
            lms_row = db.query(ModelVersion).filter_by(kind=MODEL_KIND_LMSTUDIO).one()
            check("O3 : désactivation -> LM Studio neutralisé (available False)", lms_row.available is False)
    finally:
        op.list_llm_models = orig_list

    # ====================== O4 : concurrence & robustesse ===================
    def make_predictor(max_parallel=4, retries=0):
        p = object.__new__(op.LMStudioPredictor)
        p.cfg, p.taxonomy, p.sentiment_labels = CFG, TAXO, SENT_LABELS
        p.base_url, p.model = "http://x:1234/v1", "m"
        p.temperature, p.timeout_s = 0.1, 5
        p.fallback_theme, p.prompt_version = "Autre / Non classé", "v1"
        p.max_parallel, p.retries = max_parallel, retries
        return p

    VALID = {"themes": [{"niv1": N1, "niv2": N2, "sentiment": "Neutre", "confidence": 0.8}],
             "signaux": {"rupture": False, "churn": False, "insatisfaction_forte": False}}
    orig_call = op.call_llm_chat
    try:
        # 1. Pool : ordre préservé + verbatims vides court-circuités au bon index.
        op.call_llm_chat = lambda *a, **k: dict(VALID)
        pred = make_predictor(max_parallel=4, retries=0)
        out = pred.predict_cleaned_batch(["", "texte A", "", "texte B"], [None, 5, None, 5])
        check("O4 : ordre préservé (vides aux index 0 et 2)",
              out[0]["nb_themes"] == 0 and out[2]["nb_themes"] == 0
              and out[1]["nb_themes"] >= 1 and out[3]["nb_themes"] >= 1,
              [r["nb_themes"] for r in out])
        check("O4 : tous les verbatims traités", len(out) == 4)

        # 2. Retries : échoue 2 fois puis réussit (retries=2).
        calls = {"n": 0}
        def _flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise op.LMStudioError("blip réseau")
            return dict(VALID)
        op.call_llm_chat = _flaky
        r = make_predictor(max_parallel=1, retries=2).predict_cleaned_batch(["texte"], [None])
        check("O4 : retry réussit après 2 échecs", r[0]["nb_themes"] >= 1 and calls["n"] == 3, calls["n"])

        # 3. Fail-fast : LM Studio down -> LMStudioError propagée (lot 'failed').
        op.call_llm_chat = lambda *a, **k: (_ for _ in ()).throw(op.LMStudioError("down"))
        raised = False
        try:
            make_predictor(max_parallel=4, retries=0).predict_cleaned_batch(["a", "b", "c", "d"], None)
        except op.LMStudioError:
            raised = True
        check("O4 : LM Studio down -> LMStudioError propagée (échec propre)", raised)
    finally:
        op.call_llm_chat = orig_call


if __name__ == "__main__":
    run()
    fails = [r for r in _RESULTS if r[0] == "ÉCHEC"]
    width = max(len(r[1]) for r in _RESULTS)
    for status, label, detail in _RESULTS:
        line = f"  [{status:5}] {label:<{width}}"
        if status == "ÉCHEC" and detail:
            line += f"  -> {detail}"
        print(line)
    print(f"\nRecette V4 (O1→O4) : {len(_RESULTS) - len(fails)}/{len(_RESULTS)} OK")
    sys.exit(1 if fails else 0)
