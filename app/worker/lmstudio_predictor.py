"""Moteur de classification « LM Studio » (LLM local) — V4/V5.

Troisième backend de prédiction, alternatif à CamemBERT (`VerbatimPredictor`) et
au stub heuristique (`StubPredictor`). Expose **exactement la même interface**
(`anonymizer`, `cleaner`, `batch_size`, `signal_thresholds`, `sentiment_labels`,
`predict_cleaned_batch`) afin que la tâche worker reste agnostique du moteur, et
ajoute en V5 le mode **raffineur** (`refine_cleaned_batch`) pour la cascade.

LM Studio sert une API **compatible OpenAI** (``/v1/chat/completions``,
``/v1/models``) sur l'hôte (port 1234 par défaut), avec accélération GPU Metal.

Principes (cf. docs/SPEC_V4_LMSTUDIO.md, docs/SPEC_V5_MULTI_MOTEUR.md) :
  - Appel HTTP local via la **stdlib** (``urllib``) — aucune dépendance ajoutée,
    compatible offline strict ; le worker joint LM Studio sur ``host.docker.internal``.
  - Le texte transmis est **déjà anonymisé + nettoyé** (étapes amont inchangées).
  - Sortie **JSON contrainte par schéma** (``response_format``) puis **revalidée
    contre la taxonomie** : jamais de couple niv1/niv2 hors référentiel.
  - Repli : couple invalide → sentinelle ``fallback_theme`` (« Autre / Non classé »,
    label propre au moteur, **non ajouté** à la taxonomie partagée pour ne pas
    casser CamemBERT) + **revue humaine forcée**.

NOTE testabilité : la logique de décision est isolée en fonctions PURES dans
``llm_common`` (``build_llm_prompt``, ``build_refiner_prompt``, ``map_llm_response``),
ré-exportées ici pour rétrocompatibilité. Cette classe ne fait que câbler ces
fonctions au client HTTP et aux étapes amont.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.preprocessing import Anonymizer, TextCleaner
from src.utils import Taxonomy, resolve_path

# Logique de décision PARTAGÉE (V5). Ré-exportée pour rétrocompatibilité : du code
# et des recettes existantes référencent ces symboles via ``lmstudio_predictor.X``.
from .llm_common import (  # noqa: F401  (ré-exports volontaires)
    FALLBACK_THEME_DEFAULT,
    LLM_OUTPUT_SCHEMA,
    OUTPUT_COLUMNS,
    PROMPT_VERSION_DEFAULT,
    build_llm_prompt,
    build_refiner_prompt,
    empty_output,
    map_llm_response,
)

logger = logging.getLogger("worker.lmstudio")


class LMStudioError(RuntimeError):
    """Échec d'appel au service LM Studio (réseau, HTTP, timeout). Fait échouer le lot."""


# --------------------------------------------------------------------------- #
#  Client HTTP (stdlib) — API compatible OpenAI de LM Studio
# --------------------------------------------------------------------------- #
def call_llm_chat(
    base_url: str, model: str, system: str, user: str,
    temperature: float, timeout_s: float,
) -> Dict[str, Any]:
    """Appelle LM Studio /v1/chat/completions en sortie structurée. Lève LMStudioError sur échec."""
    # Certains modèles (ex. Mistral 7B Instruct) ont un template de chat qui
    # n'accepte PAS le rôle "system" (« Only user and assistant roles are
    # supported »). On fusionne donc les consignes dans le message "user" :
    # universel, compatible avec ou sans support du rôle system.
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": f"{system}\n\n{user}"},
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

    def _call_with_retries(self, prompt: Dict[str, str], cleaned_text: str,
                           satisfaction: Optional[float]) -> Dict[str, Any]:
        """Appelle le LLM avec retries puis revalide -> sortie OUTPUT_COLUMNS.

        Une erreur de connexion persistante (après ``retries``) lève LMStudioError :
        elle remonte jusqu'à la tâche worker qui marque le lot 'failed' (échec propre).
        Une réponse JSON malformée n'est PAS une LMStudioError (gérée par le repli).
        """
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

    def _predict_one(self, cleaned_text: str, satisfaction: Optional[float]) -> Dict[str, Any]:
        """Prédit un verbatim (mode proposeur), avec retries sur erreur transitoire."""
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_llm_prompt(
            self.taxonomy, cleaned_text, satisfaction, self.fallback_theme, self.prompt_version)
        return self._call_with_retries(prompt, cleaned_text, satisfaction)

    def _refine_one(self, cleaned_text: str, satisfaction: Optional[float],
                    proposal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Raffine un verbatim (mode raffineur) à partir de la proposition du moteur 1."""
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_refiner_prompt(
            self.taxonomy, cleaned_text, proposal, satisfaction,
            self.fallback_theme, self.prompt_version)
        return self._call_with_retries(prompt, cleaned_text, satisfaction)

    def _run_pool(self, n: int, submit) -> List[Dict[str, Any]]:
        """Exécute ``submit(i)`` pour i ∈ [0, n) en pool borné, ordre préservé.

        Concurrence BORNÉE (``max_parallel``) : appels I/O-bound parallélisés via
        un pool de threads (urllib relâche le GIL en attente réseau). **Fail-fast** :
        la première LMStudioError annule les appels en attente et est propagée.
        """
        results: List[Optional[Dict[str, Any]]] = [None] * n
        if n == 0:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_parallel, n)) as executor:
            futures = {executor.submit(submit, i): i for i in range(n)}
            try:
                for fut in as_completed(futures):
                    results[futures[fut]] = fut.result()
            except LMStudioError:
                for f in futures:           # échec propre : ne pas démarrer le reste
                    f.cancel()
                raise
        return results  # type: ignore[return-value]

    def predict_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[list] = None,
    ) -> List[Dict[str, Any]]:
        """Prédit à partir de textes DÉJÀ anonymisés + nettoyés (mode proposeur).

        Concurrence bornée, ordre des résultats préservé, fail-fast (la première
        LMStudioError -> lot 'failed').
        """
        if satisfactions is None:
            satisfactions = [None] * len(cleaned)
        return self._run_pool(len(cleaned),
                              lambda i: self._predict_one(cleaned[i], satisfactions[i]))

    def refine_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[list],
        proposals: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Raffine des prédictions (cascade V5) à partir de textes DÉJÀ anonymisés.

        Pour chaque verbatim, appelle le LLM en mode raffineur avec la proposition
        du moteur 1 (``proposals[i]``) puis revalide via ``map_llm_response``. Même
        contrat de sortie que ``predict_cleaned_batch`` (OUTPUT_COLUMNS), même
        concurrence bornée / ordre préservé / fail-fast. cf. SPEC_V5 §6 (cascade).
        """
        n = len(cleaned)
        if satisfactions is None:
            satisfactions = [None] * n
        return self._run_pool(n,
                              lambda i: self._refine_one(cleaned[i], satisfactions[i], proposals[i]))
