#!/usr/bin/env python3
"""Recette V4 — moteur LM Studio (LLM local).

Vérifie le moteur LM Studio de bout en bout SANS service réel (HTTP mocké) et SANS
torch (fonctions pures de mapping/validation). Couvre les lots O1 à O5.

- O1 : gabarit de sortie (OUTPUT_COLUMNS), prompt (taxo injectée), mapping
  couple valide / repli, signaux, verbatim vide, client HTTP (parse/erreur).
- O2 : matching tolérant (casse/accents), 2 plafonds de confiance, dé-doublonnage,
  conflit de sentiment, prompt versionné.
- O3 : détection LM Studio (`/v1/models`), `available` dynamique, synchro registre.
- O4 : pool borné (ordre préservé), retries, fail-fast (échec propre si down).
- O5 : taxonomie Cultura 2026, prompts proposeur/raffineur V2 et contrat D-26.

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
TAXO_2026 = Taxonomy.from_json(ROOT / "data/models/cultura_2026/taxonomy.json")
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

CFG_2026 = {
    "thresholds": {"revue_humaine": 0.70, "max_themes": 2},
    "signals": {"insatisfaction_score_max": 3},
    "lmstudio": {
        "contract_version": "cultura_2026",
        "prompt_version": "v2-cultura-2026",
        "fallback_theme": "Général",
        "fallback_niv2": "Autre",
        "guardrails": {
            "repli_confidence_max": 0.40,
            "invalid_json_confidence_max": 0.30,
            "review_on_sentiment_conflict": True,
        },
    },
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

    # ================= O5 : contrat Cultura 2026 ============================
    p26 = op.build_llm_prompt(
        TAXO_2026, "paiement impossible mais recherche facile", 2,
        "Général", "v2-cultura-2026", "Autre")
    check("O5 : prompt V2 tracé", "[prompt v2-cultura-2026]" in p26["system"])
    check("O5 : prompt V2 porte la règle bi-thème",
          "deux sujets distincts" in p26["system"] and "hésitation" in p26["system"])
    check("O5 : prompt V2 porte le sentiment unique et la priorité au négatif",
          "sentiment est unique" in p26["system"] and "aspect négatif" in p26["system"])
    check("O5 : note Cultura injectée sur l'échelle 1-4", "(1-4) : 2" in p26["user"])
    check("O5 : nouveau référentiel 11/59 injecté",
          "Réception commande" in p26["user"] and "Etat colis, produit" in p26["user"]
          and "Tunnel de vente - Paiement" not in p26["user"])
    check("O5 : repli canonique présent dans le prompt",
          'niv1="Général", niv2="Autre"' in p26["user"])

    r26_prompt = op.build_refiner_prompt(
        TAXO_2026, "bug mais accueil magasin agréable", {}, 1,
        "Général", "v2-cultura-2026", "Autre")
    check("O5 : prompt raffineur V2 tracé",
          "[prompt v2-cultura-2026 · raffineur]" in r26_prompt["system"])
    check("O5 : raffineur applique D-26 et l'échelle 1-4",
          "uniquement le ou les thèmes négatifs" in r26_prompt["system"]
          and "(1-4) : 1" in r26_prompt["user"])

    bug_n2 = TAXO_2026.children["Bug"][0]
    espace_n2 = TAXO_2026.children["Espace client"][0]
    raw_two = {"themes": [
        {"niv1": "Bug", "niv2": bug_n2, "sentiment": "Négatif", "confidence": 0.91},
        {"niv1": "Espace client", "niv2": espace_n2, "sentiment": "Négatif", "confidence": 0.82},
    ], "signaux": {}}
    r_two = op.map_llm_response(raw_two, "deux problèmes", 2, TAXO_2026, CFG_2026, SENT_LABELS)
    check("O5 : deux sujets distincts de même sentiment sont conservés",
          r_two["nb_themes"] == 2)
    check("O5 : sentiment unique recopié sur les deux thèmes",
          r_two["theme1_sentiment"] == r_two["theme2_sentiment"] == "Négatif")

    raw_mixed = {"themes": [
        {"niv1": "Bug", "niv2": bug_n2, "sentiment": "Négatif", "confidence": 0.91},
        {"niv1": "Espace client", "niv2": espace_n2, "sentiment": "Positif", "confidence": 0.82},
    ], "signaux": {}}
    r_mixed = op.map_llm_response(
        raw_mixed, "bug mais espace client pratique", 2, TAXO_2026, CFG_2026, SENT_LABELS)
    check("O5 : cas mixte conserve uniquement le thème négatif (D-26)",
          r_mixed["nb_themes"] == 1 and r_mixed["theme1_niv1"] == "Bug")
    check("O5 : cas mixte force la revue", r_mixed["revue_humaine_requise"] is True)

    raw_invalid_26 = {"themes": [{
        "niv1": "Ancien thème", "niv2": "Ancien sous-thème",
        "sentiment": "Neutre", "confidence": 0.95,
    }], "signaux": {}}
    r_invalid_26 = op.map_llm_response(
        raw_invalid_26, "texte ambigu", None, TAXO_2026, CFG_2026, SENT_LABELS)
    check("O5 : repli V2 reste dans le référentiel 11/59",
          r_invalid_26["theme1_niv1"] == "Général"
          and r_invalid_26["theme1_niv2"] == "Autre"
          and TAXO_2026.is_valid_pair(r_invalid_26["theme1_niv1"], r_invalid_26["theme1_niv2"]))

    # --- 10. Client HTTP : parse OK (urlopen mocké) --------------------------
    import io
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
        captured_payloads = []
        def _ok(req, timeout=None):
            captured_payloads.append(_json.loads(req.data.decode("utf-8")))
            return _FakeResp({"choices": [{"message": {"content": content}}]})
        op.urllib.request.urlopen = _ok
        parsed = op.call_llm_chat("http://x:1234/v1", "m", "sys", "usr", 0.1, 5)
        check("client : parse JSON OK (choices OpenAI)", isinstance(parsed, dict) and parsed.get("themes"), parsed)
        check("client : schéma JSON et max_tokens transmis",
              captured_payloads[-1]["response_format"]["type"] == "json_schema"
              and "max_tokens" not in captured_payloads[-1])

        op.call_llm_chat(
            "http://x:1234/v1", "m", "sys", "usr", 0.1, 5,
            response_format_mode="json_object", max_tokens=123)
        check("client : mode json_object de compatibilité + borne de sortie",
              captured_payloads[-1]["response_format"] == {"type": "json_object"}
              and captured_payloads[-1]["max_tokens"] == 123)

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

        def _http_500(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 500, "Internal Server Error", {},
                io.BytesIO(b"<html> Internal Server Error </html>"))
        op.urllib.request.urlopen = _http_500
        try:
            op.call_llm_chat("http://x:1234/v1", "m", "s", "u", 0.1, 5)
            status_500_ok = False
        except op.LMStudioError as exc:
            status_500_ok = exc.status_code == 500 and exc.retryable and "format=json_schema" in str(exc)
        check("client : HTTP 500 est marqué transitoire et diagnostiqué", status_500_ok)
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

        cfg_lms_26 = {"lmstudio": {
            "enabled": True, "model": "mon-modele", "base_url": "http://x:1234/v1",
            "taxonomy": str(ROOT / "data/models/cultura_2026/taxonomy.json"),
            "prompt_version": "v2-cultura-2026", "contract_version": "cultura_2026",
        }}
        d26 = mr._detect_lmstudio(cfg_lms_26)
        check("O3/O5 : registre publie le référentiel LM Studio",
              d26["metrics"]["taxonomy_present"] is True
              and d26["metrics"]["taxonomy_path"].endswith("cultura_2026/taxonomy.json"))
        check("O3/O5 : registre publie les versions de prompt et contrat",
              d26["metrics"]["prompt_version"] == "v2-cultura-2026"
              and d26["metrics"]["contract_version"] == "cultura_2026")

        cfg_lms_missing_taxo = {"lmstudio": {
            "enabled": True, "model": "mon-modele", "base_url": "http://x:1234/v1",
            "taxonomy": str(ROOT / "data/models/introuvable/taxonomy.json"),
        }}
        d_missing_taxo = mr._detect_lmstudio(cfg_lms_missing_taxo)
        check("O3/O5 : référentiel absent -> LM Studio indisponible",
              d_missing_taxo["available"] is False
              and d_missing_taxo["metrics"]["taxonomy_present"] is False)

        from worker.config_worker import build_worker_cfg

        previous_parallel = os.environ.get("LMSTUDIO_MAX_PARALLEL")
        os.environ["LMSTUDIO_MAX_PARALLEL"] = "1"
        try:
            container_cfg = build_worker_cfg()
        finally:
            if previous_parallel is None:
                os.environ.pop("LMSTUDIO_MAX_PARALLEL", None)
            else:
                os.environ["LMSTUDIO_MAX_PARALLEL"] = previous_parallel
        check("O5 : chemin taxonomie LM réécrit vers le volume modèles",
              str(container_cfg["lmstudio"]["taxonomy"]).endswith(
                  "/cultura_2026/taxonomy.json")
              and not str(container_cfg["lmstudio"]["taxonomy"]).startswith("data/models/"),
              container_cfg["lmstudio"]["taxonomy"])
        check("O5 : concurrence LM Studio lue depuis l'environnement Docker",
              container_cfg["lmstudio"]["max_parallel"] == 1,
              container_cfg["lmstudio"]["max_parallel"])
        # Incident du 19/09/2026 (Lot 21, HTTP 500) : le repli de schéma déclaré en
        # configuration doit rester "none" — "json_object" est refusé (HTTP 400) par
        # LM Studio sur ce poste. Un retour à "json_object" romprait silencieusement
        # le repli en production.
        check("O5 : repli de schéma configuré = 'none' (pas 'json_object', refusé par LM Studio)",
              container_cfg["lmstudio"].get("response_format_fallback") == "none",
              container_cfg["lmstudio"].get("response_format_fallback"))

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
    def make_predictor(max_parallel=1, retries=0, warmup=False):
        p = object.__new__(op.LMStudioPredictor)
        p.cfg, p.taxonomy, p.sentiment_labels = CFG, TAXO, SENT_LABELS
        p.base_url, p.model = "http://x:1234/v1", "m"
        p.temperature, p.timeout_s = 0.1, 5
        p.fallback_theme, p.prompt_version = "Autre / Non classé", "v1"
        p.max_parallel, p.retries = max_parallel, retries
        p.max_tokens = 128
        p.retry_backoff_s, p.retry_backoff_max_s = 0.0, 0.0
        p.response_format_mode, p.response_format_fallback = "json_schema", "none"
        p.warmup_enabled, p._warmup_done = warmup, False
        p._warmup_lock = op.threading.Lock()
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

        # 2. Échauffement : un appel technique unique précède la rafale métier.
        warmup_calls = []
        def _warmup_call(*args, **kwargs):
            warmup_calls.append((args[3], kwargs.get("response_format_mode")))
            return dict(VALID)
        op.call_llm_chat = _warmup_call
        out_warmup = make_predictor(warmup=True).predict_cleaned_batch(["texte"], [None])
        check("O4 : échauffement séquentiel unique avant classification",
              len(warmup_calls) == 2 and warmup_calls[0][0] == op._WARMUP_USER
              and out_warmup[0]["nb_themes"] == 1, warmup_calls)

        # 3. Retries : échoue 2 fois puis réussit (retries=2), sans rafale immédiate
        # dans la recette grâce à un backoff à zéro.
        calls = {"n": 0}
        def _flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise op.LMStudioError("blip réseau")
            return dict(VALID)
        op.call_llm_chat = _flaky
        r = make_predictor(max_parallel=1, retries=2).predict_cleaned_batch(["texte"], [None])
        check("O4 : retry réussit après 2 échecs", r[0]["nb_themes"] >= 1 and calls["n"] == 3, calls["n"])

        # 4. Repli de compatibilité : après un refus durable du schéma (500),
        # "none" est tenté puis repasse dans le mapper taxonomique. "none" (et non
        # "json_object") est le repli configuré par défaut : testé en direct le
        # 19/09/2026, ce LM Studio (Qwen2.5-VL-7B-Instruct) refuse "json_object"
        # en HTTP 400 ("must be 'json_schema' or 'text'") mais accepte "none".
        modes = []
        def _schema_refused(*args, **kwargs):
            mode = kwargs.get("response_format_mode")
            modes.append(mode)
            if mode == "json_schema":
                raise op.LMStudioError("grammar refused", status_code=500, retryable=True,
                                      response_format_mode=mode)
            return dict(VALID)
        op.call_llm_chat = _schema_refused
        fallback_out = make_predictor(retries=0).predict_cleaned_batch(["texte"], [None])
        check("O4 : HTTP 500 schéma -> repli 'none' contrôlé",
              modes == ["json_schema", "none"] and fallback_out[0]["theme1_niv1"] == N1,
              modes)

        # 5. Fail-fast : LM Studio down -> LMStudioError propagée (lot 'failed').
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
    print(f"\nRecette V4 (O1→O5) : {len(_RESULTS) - len(fails)}/{len(_RESULTS)} OK")
    sys.exit(1 if fails else 0)
