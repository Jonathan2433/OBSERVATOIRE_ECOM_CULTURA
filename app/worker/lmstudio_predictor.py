"""Moteur de classification « LM Studio » (LLM local) — V4.

Troisième backend de prédiction, alternatif à CamemBERT (`VerbatimPredictor`) et
au stub heuristique (`StubPredictor`). Expose **exactement la même interface**
(`anonymizer`, `cleaner`, `batch_size`, `signal_thresholds`, `sentiment_labels`,
`predict_cleaned_batch`) afin que la tâche worker reste agnostique du moteur.

LM Studio sert une API **compatible OpenAI** (``/v1/chat/completions``,
``/v1/models``) sur l'hôte (port 1234 par défaut), avec accélération GPU Metal.

Principes (cf. docs/SPEC_V4_LMSTUDIO.md) :
  - Appel HTTP local via la **stdlib** (``urllib``) — aucune dépendance ajoutée,
    compatible offline strict ; le worker joint LM Studio sur ``host.docker.internal``.
  - Le texte transmis est **déjà anonymisé + nettoyé** (étapes amont inchangées).
  - Sortie **JSON contrainte par schéma** (``response_format``) puis **revalidée
    contre la taxonomie** : jamais de couple niv1/niv2 hors référentiel.
  - Repli : couple invalide → sentinelle ``fallback_theme`` (« Autre / Non classé »,
    label propre au moteur, **non ajouté** à la taxonomie partagée pour ne pas
    casser CamemBERT) + **revue humaine forcée**.

NOTE testabilité : la logique de décision est isolée en fonctions PURES
(``build_llm_prompt``, ``map_llm_response``) testables sans torch/spaCy.
La classe ne fait que câbler ces fonctions au client HTTP et aux étapes amont.
"""
from __future__ import annotations

import json
import logging
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from src.preprocessing import Anonymizer, TextCleaner
from src.utils import Taxonomy, resolve_path

logger = logging.getLogger("worker.lmstudio")

# Gabarit de sortie — MIROIR de src.inference.predictor.OUTPUT_COLUMNS.
# Répliqué ici volontairement pour rester torch-free (predictor.py importe torch).
OUTPUT_COLUMNS = [
    "verbatim_analysé",
    "nb_themes",
    "theme1_niv1", "theme1_niv2", "theme1_sentiment", "theme1_score_confiance",
    "theme2_niv1", "theme2_niv2", "theme2_sentiment", "theme2_score_confiance",
    "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte",
    "confidence_globale", "revue_humaine_requise",
]

FALLBACK_THEME_DEFAULT = "Autre / Non classé"

# Schéma JSON imposé au LLM (sortie structurée OpenAI/LM Studio). Garantit la
# forme ; la validité métier (taxonomie), la limite à 2 thèmes et le plafonnement
# de confiance sont assurés ENSUITE côté worker (map_llm_response). On reste donc
# sur le sous-ensemble de JSON-schema supporté par la grammaire de LM Studio
# (llama.cpp) : type / enum / required / properties — SANS minItems/maxItems/
# minimum/maximum, qui provoquent un HTTP 500 « grammar » sur LM Studio.
LLM_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "niv1": {"type": "string"},
                    "niv2": {"type": "string"},
                    "sentiment": {"type": "string", "enum": ["Négatif", "Neutre", "Positif"]},
                    "confidence": {"type": "number"},
                },
                "required": ["niv1", "niv2", "sentiment", "confidence"],
            },
        },
        "signaux": {
            "type": "object",
            "properties": {
                "rupture": {"type": "boolean"},
                "churn": {"type": "boolean"},
                "insatisfaction_forte": {"type": "boolean"},
            },
            "required": ["rupture", "churn", "insatisfaction_forte"],
        },
    },
    "required": ["themes", "signaux"],
}


class LMStudioError(RuntimeError):
    """Échec d'appel au service LM Studio (réseau, HTTP, timeout). Fait échouer le lot."""


# --------------------------------------------------------------------------- #
#  Gabarit de sortie
# --------------------------------------------------------------------------- #
def empty_output(cleaned_text: str) -> Dict[str, Any]:
    """Sortie neutre (verbatim non classifiable) -> revue humaine."""
    return {
        "verbatim_analysé": cleaned_text or "",
        "nb_themes": 0,
        "theme1_niv1": "", "theme1_niv2": "", "theme1_sentiment": "",
        "theme1_score_confiance": 0.0,
        "theme2_niv1": "", "theme2_niv2": "", "theme2_sentiment": "",
        "theme2_score_confiance": "",
        "signal_rupture_client": False, "signal_churn": False,
        "signal_insatisfaction_forte": False,
        "confidence_globale": 0.0, "revue_humaine_requise": True,
    }


# --------------------------------------------------------------------------- #
#  PROMPT (pur) — versionné via cfg.lmstudio.prompt_version
# --------------------------------------------------------------------------- #
PROMPT_VERSION_DEFAULT = "v1"


def _taxonomy_block(taxonomy: Taxonomy) -> str:
    lines = []
    for niv1 in taxonomy.niv1_labels:
        children = ", ".join(taxonomy.children.get(niv1, []))
        lines.append(f"- {niv1} : {children}")
    return "\n".join(lines)


def build_llm_prompt(
    taxonomy: Taxonomy, cleaned_text: str, satisfaction: Optional[float],
    fallback_theme: str = FALLBACK_THEME_DEFAULT, version: str = PROMPT_VERSION_DEFAULT,
) -> Dict[str, str]:
    """Construit (system, user) pour /v1/chat/completions. Fonction pure et versionnée.

    Le numéro de version est tracé dans le system prompt pour reproductibilité.
    Pour faire évoluer la formulation, ajouter une branche ``version`` ici.
    """
    system = (
        f"[prompt {version}] Tu es un classifieur de verbatims clients e-commerce pour "
        "Cultura. Tu classes chaque verbatim STRICTEMENT dans la taxonomie fournie, sans "
        "jamais inventer de thème. Tu réponds UNIQUEMENT en JSON conforme au schéma "
        "demandé, sans aucun texte autour."
    )
    sat_line = ""
    if satisfaction is not None:
        try:
            sat_line = f"\nNote de satisfaction (1-10) : {int(round(float(satisfaction)))}"
        except (ValueError, TypeError):
            sat_line = ""
    user = (
        "Taxonomie autorisée (niv1 : sous-thèmes niv2 valides) :\n"
        f"{_taxonomy_block(taxonomy)}\n\n"
        "Règles impératives :\n"
        "1. Choisis 1 thème, ou 2 SEULEMENT si le verbatim aborde deux sujets DISTINCTS.\n"
        "2. Recopie les libellés niv1 et niv2 EXACTEMENT comme ci-dessus (un couple doit "
        "toujours être un sous-thème listé sous son niv1).\n"
        "3. N'invente JAMAIS de thème. Si rien ne correspond, mets niv1="
        f"\"{fallback_theme}\" et niv2=\"\".\n"
        "4. sentiment ∈ {Négatif, Neutre, Positif}. confidence ∈ [0,1], HONNÊTE : basse "
        "si tu hésites ou si le verbatim est ambigu.\n"
        "5. signaux : rupture (le client annonce rompre la relation / partir à la "
        "concurrence), churn (risque de départ), insatisfaction_forte.\n\n"
        f"Verbatim à classer :{sat_line}\n\"\"\"\n{cleaned_text}\n\"\"\""
    )
    return {"system": system, "user": user}


# --------------------------------------------------------------------------- #
#  MAPPING réponse -> sortie (pur) — validation taxonomie + repli + garde-fous
# --------------------------------------------------------------------------- #
def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except (ValueError, TypeError):
        return 0.0
    return max(0.0, min(1.0, v))


def _valid_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, float) and value != value:  # NaN
            return None
        return int(round(float(value)))
    except (ValueError, TypeError):
        return None


def _norm(s: Any) -> str:
    """Normalise un libellé pour un appariement tolérant (casse + accents + espaces).

    Permet de retrouver le libellé canonique de la taxonomie même si le LLM
    altère la casse ou les accents — sans jamais « deviner » un thème : on
    n'accepte que ce qui correspond à un libellé EXISTANT après normalisation.
    """
    txt = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return " ".join(txt.split()).casefold()


def _canon_map(labels: List[str]) -> Dict[str, str]:
    """Table normalisé -> libellé canonique (dernier gagne en cas de collision rare)."""
    return {_norm(l): l for l in labels}


def map_llm_response(
    raw: Dict[str, Any],
    cleaned_text: str,
    satisfaction: Optional[float],
    taxonomy: Taxonomy,
    cfg: Dict[str, Any],
    sentiment_labels: List[str],
) -> Dict[str, Any]:
    """Transforme la réponse JSON du LLM en dict de sortie validé. Fonction pure.

    Étapes : appariement TOLÉRANT des libellés (casse/accents) à la taxonomie ->
    repli + revue forcée si hors référentiel -> dé-doublonnage -> garde-fous de
    confiance (deux plafonds) -> désaccord de sentiment -> assemblage.
    """
    if not cleaned_text or str(cleaned_text).strip() == "":
        return empty_output(cleaned_text)

    engine = cfg.get("lmstudio", {}) or {}
    guards = engine.get("guardrails", {}) or {}
    fallback_theme = engine.get("fallback_theme", FALLBACK_THEME_DEFAULT)
    repli_cap = float(guards.get("repli_confidence_max", 0.40))
    bad_json_cap = float(guards.get("invalid_json_confidence_max", 0.30))
    review_on_conflict = bool(guards.get("review_on_sentiment_conflict", True))
    max_themes = int(cfg.get("thresholds", {}).get("max_themes", 2))
    seuil = float(cfg.get("thresholds", {}).get("revue_humaine", 0.50))
    score_max = int(cfg.get("signals", {}).get("insatisfaction_score_max", 3))

    sent_canon = _canon_map(sentiment_labels)
    niv1_canon = _canon_map(taxonomy.niv1_labels)

    themes_in = raw.get("themes") if isinstance(raw, dict) else None
    if not isinstance(themes_in, list) or not themes_in:
        # Réponse hors-forme (JSON cassé / vide) -> repli au plafond le plus bas + revue.
        return _assemble(cleaned_text, [_fallback_theme(fallback_theme, bad_json_cap)],
                         raw.get("signaux", {}) if isinstance(raw, dict) else {},
                         satisfaction, score_max, seuil, forced_review=True)

    mapped: List[Dict[str, Any]] = []
    forced_review = False
    for t in themes_in[:max_themes]:
        t = t if isinstance(t, dict) else {}
        conf = _clamp01(t.get("confidence", 0.0))

        # Sentiment : appariement tolérant -> sinon Neutre + revue.
        cs = sent_canon.get(_norm(t.get("sentiment", "")))
        if cs is None:
            cs = "Neutre"
            conf = min(conf, repli_cap)
            forced_review = True

        # Couple niv1/niv2 : appariement tolérant contre la taxonomie.
        canon_niv1 = niv1_canon.get(_norm(t.get("niv1", "")))
        canon_niv2 = None
        if canon_niv1 is not None:
            canon_niv2 = _canon_map(taxonomy.children.get(canon_niv1, [])).get(_norm(t.get("niv2", "")))

        if canon_niv1 is not None and canon_niv2 is not None:
            mapped.append({"niv1": canon_niv1, "niv2": canon_niv2, "sentiment": cs, "conf": conf})
        else:
            # Hors référentiel -> sentinelle de repli (décision a+c) + revue forcée.
            fb = _fallback_theme(fallback_theme, min(conf, repli_cap))
            fb["sentiment"] = cs
            mapped.append(fb)
            forced_review = True

    # Dé-doublonnage des couples identiques (garde la 1re occurrence).
    deduped: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for m in mapped:
        key = (m["niv1"], m["niv2"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    if not deduped:
        deduped = [_fallback_theme(fallback_theme, repli_cap)]
        forced_review = True

    # Garde-fou : 2 thèmes au sentiment divergent (dont un Négatif) -> revue.
    if review_on_conflict and len(deduped) == 2:
        sents = {deduped[0]["sentiment"], deduped[1]["sentiment"]}
        if len(sents) > 1 and "Négatif" in sents:
            forced_review = True

    return _assemble(cleaned_text, deduped,
                     raw.get("signaux", {}) if isinstance(raw, dict) else {},
                     satisfaction, score_max, seuil, forced_review)


def _fallback_theme(label: str, conf: float) -> Dict[str, Any]:
    return {"niv1": label, "niv2": "", "sentiment": "Neutre", "conf": float(conf)}


def _assemble(
    cleaned_text: str, themes: List[Dict[str, Any]], signaux: Dict[str, Any],
    satisfaction: Optional[float], score_max: int, seuil: float, forced_review: bool,
) -> Dict[str, Any]:
    t1 = themes[0]
    sg = signaux if isinstance(signaux, dict) else {}
    rupture = bool(sg.get("rupture", False))
    churn = bool(sg.get("churn", False)) or rupture        # rupture => churn (parité moteurs)
    insat = bool(sg.get("insatisfaction_forte", False))
    si = _valid_int(satisfaction)
    if si is not None and si <= score_max and t1["sentiment"] == "Négatif":
        insat = True                                        # règle métier déterministe

    confidence_globale = float(t1["conf"])
    revue = bool(forced_review or confidence_globale < seuil)

    out = empty_output(cleaned_text)
    out.update({
        "verbatim_analysé": cleaned_text,
        "nb_themes": len(themes),
        "theme1_niv1": t1["niv1"],
        "theme1_niv2": t1["niv2"],
        "theme1_sentiment": t1["sentiment"],
        "theme1_score_confiance": round(confidence_globale, 4),
        "signal_rupture_client": rupture,
        "signal_churn": churn,
        "signal_insatisfaction_forte": insat,
        "confidence_globale": round(confidence_globale, 4),
        "revue_humaine_requise": revue,
    })
    if len(themes) == 2:
        t2 = themes[1]
        out.update({
            "theme2_niv1": t2["niv1"],
            "theme2_niv2": t2["niv2"],
            "theme2_sentiment": t2["sentiment"],
            "theme2_score_confiance": round(float(t2["conf"]), 4),
        })
    return out


# --------------------------------------------------------------------------- #
#  Client HTTP (stdlib) — API compatible OpenAI de LM Studio
# --------------------------------------------------------------------------- #
def call_llm_chat(
    base_url: str, model: str, system: str, user: str,
    temperature: float, timeout_s: float,
) -> Dict[str, Any]:
    """Appelle LM Studio /v1/chat/completions en sortie structurée. Lève LMStudioError sur échec."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": temperature,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "verbatim_classification", "strict": False, "schema": LLM_OUTPUT_SCHEMA},
        },
    }
    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (URL locale)
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # serveur joignable mais erreur (ex. 500 grammaire)
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        raise LMStudioError(f"LM Studio a renvoyé HTTP {exc.code} ({url}) : {detail}") from exc
    except urllib.error.URLError as exc:
        raise LMStudioError(f"LM Studio injoignable ({url}) : {exc}") from exc
    except (TimeoutError, OSError) as exc:
        raise LMStudioError(f"LM Studio timeout/erreur réseau ({url}) : {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = ""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        # JSON malformé malgré le schéma : la couche mapping appliquera le repli.
        logger.warning("Réponse LM Studio non-JSON : %s", exc)
        return {}


def list_llm_models(base_url: str, timeout_s: float = 5) -> List[str]:
    """Liste les modèles chargés sur LM Studio (GET /v1/models). Lève LMStudioError si injoignable."""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (URL locale)
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise LMStudioError(f"LM Studio injoignable ({url}) : {exc}") from exc
    return [m.get("id", "") for m in body.get("data", []) if isinstance(m, dict)]


def model_is_installed(model: str, installed: List[str]) -> bool:
    """Vrai si ``model`` figure parmi les modèles chargés (tolérant au suffixe)."""
    if model in installed:
        return True
    base = model.split(":")[0]
    return any(n == base or n.startswith(base) for n in installed)


# --------------------------------------------------------------------------- #
#  Prédicteur (orchestration)
# --------------------------------------------------------------------------- #
class LMStudioPredictor:
    """Backend LLM local (LM Studio) — interface compatible VerbatimPredictor / StubPredictor."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))
        self.anonymizer = Anonymizer(cfg)
        self.cleaner = TextCleaner(cfg)
        self.batch_size = cfg["model"]["batch_size_inference"]
        self.sentiment_labels = cfg["sentiment"]["labels"]
        self.signal_thresholds = {
            "rupture": cfg["thresholds"]["signal_rupture"],
            "churn": cfg["thresholds"]["signal_churn"],
            "insatisfaction": cfg["thresholds"]["signal_insatisfaction"],
        }
        engine = cfg.get("lmstudio", {}) or {}
        self.base_url = engine.get("base_url", "http://host.docker.internal:1234/v1")
        self.model = engine.get("model", "local-model")
        self.temperature = float(engine.get("temperature", 0.1))
        self.timeout_s = float(engine.get("timeout_s", 120))
        self.fallback_theme = engine.get("fallback_theme", FALLBACK_THEME_DEFAULT)
        self.prompt_version = str(engine.get("prompt_version", PROMPT_VERSION_DEFAULT))
        self.max_parallel = max(1, int(engine.get("max_parallel", 4)))
        self.retries = max(0, int(engine.get("retries", 2)))
        logger.info("Moteur LM Studio : modèle=%s url=%s prompt=%s parallèle=%d",
                    self.model, self.base_url, self.prompt_version, self.max_parallel)

    def _predict_one(self, cleaned_text: str, satisfaction: Optional[float]) -> Dict[str, Any]:
        """Prédit un verbatim, avec retries sur erreur transitoire LM Studio.

        Une erreur de connexion persistante (après ``retries``) lève LMStudioError :
        elle remonte jusqu'à la tâche worker qui marque le lot 'failed' (échec propre).
        Une réponse JSON malformée n'est PAS une LMStudioError (gérée par le repli).
        """
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_llm_prompt(
            self.taxonomy, cleaned_text, satisfaction, self.fallback_theme, self.prompt_version)
        last_exc: Optional[LMStudioError] = None
        for attempt in range(self.retries + 1):
            try:
                raw = call_llm_chat(
                    self.base_url, self.model, prompt["system"], prompt["user"],
                    self.temperature, self.timeout_s)
                return map_llm_response(
                    raw, cleaned_text, satisfaction, self.taxonomy, self.cfg, self.sentiment_labels)
            except LMStudioError as exc:
                last_exc = exc
                if attempt < self.retries:
                    logger.warning("Appel LM Studio échoué (tentative %d/%d) : %s",
                                   attempt + 1, self.retries + 1, exc)
        raise last_exc  # type: ignore[misc]

    def predict_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[list] = None,
    ) -> List[Dict[str, Any]]:
        """Prédit à partir de textes DÉJÀ anonymisés + nettoyés.

        Concurrence BORNÉE (``max_parallel``) : appels I/O-bound parallélisés via
        un pool de threads (urllib relâche le GIL en attente réseau). L'ordre des
        résultats est préservé. **Fail-fast** : la première LMStudioError (service
        injoignable) annule les appels en attente et est propagée -> lot 'failed'.
        """
        if satisfactions is None:
            satisfactions = [None] * len(cleaned)
        n = len(cleaned)
        results: List[Optional[Dict[str, Any]]] = [None] * n
        if n == 0:
            return []

        with ThreadPoolExecutor(max_workers=min(self.max_parallel, n)) as executor:
            futures = {
                executor.submit(self._predict_one, cleaned[i], satisfactions[i]): i
                for i in range(n)
            }
            try:
                for fut in as_completed(futures):
                    results[futures[fut]] = fut.result()
            except LMStudioError:
                for f in futures:           # échec propre : ne pas démarrer le reste
                    f.cancel()
                raise
        return results  # type: ignore[return-value]
