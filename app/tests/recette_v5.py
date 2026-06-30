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
for p in (str(ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Base SQLite éphémère AVANT tout import éventuel de common.db (parité avec les
# autres recettes ; inoffensif si non utilisée par la section courante).
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(tempfile.mkdtemp(prefix='recette_v5_'))/'r5.db'}")

from src.utils import Taxonomy  # noqa: E402
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


if __name__ == "__main__":
    run()
    fails = [r for r in _RESULTS if r[0] == "ÉCHEC"]
    width = max(len(r[1]) for r in _RESULTS)
    for status, label, detail in _RESULTS:
        line = f"  [{status:5}] {label:<{width}}"
        if status == "ÉCHEC" and detail:
            line += f"  -> {detail}"
        print(line)
    print(f"\nRecette V5 (C1) : {len(_RESULTS) - len(fails)}/{len(_RESULTS)} OK")
    sys.exit(1 if fails else 0)
