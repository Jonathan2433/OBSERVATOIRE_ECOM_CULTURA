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
  - Contrat Cultura 2026 : taxonomie 11/59 dédiée, un thème par défaut, bi-thème
    seulement pour deux sujets explicites, sentiment unique et priorité au négatif.
  - Repli V2 : couple invalide → couple canonique ``Général / Autre`` du nouveau
    référentiel + **revue humaine forcée**. La sentinelle historique reste utilisée
    uniquement par le contrat V1.

NOTE testabilité : la logique de décision est isolée en fonctions PURES dans
``llm_common`` (``build_llm_prompt``, ``build_refiner_prompt``, ``map_llm_response``),
ré-exportées ici pour rétrocompatibilité. Cette classe ne fait que câbler ces
fonctions au client HTTP et aux étapes amont.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
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
    PROMPT_VERSION_CULTURA_2026,
    build_label_normalizer,
    build_llm_prompt,
    build_refiner_prompt,
    empty_output,
    map_llm_response,
)

logger = logging.getLogger("worker.lmstudio")


class LMStudioError(RuntimeError):
    """Échec d'appel LM Studio enrichi pour décider d'un retry sans exposer le prompt."""

    def __init__(self, message: str, *, status_code: Optional[int] = None,
                 retryable: bool = True, response_format_mode: str = "json_schema"):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.response_format_mode = response_format_mode


_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_SCHEMA_FALLBACK_HTTP_STATUS = {400, 422, 500}
_WARMUP_SYSTEM = (
    "Test technique de disponibilité du moteur local. Réponds uniquement avec le JSON "
    "conforme au schéma demandé, sans commentaire."
)
_WARMUP_USER = (
    "Ne traite aucune donnée client. Retourne un thème Général / Autre, le sentiment "
    "Neutre, une confidence à 0.5 et les trois signaux à false."
)


# --------------------------------------------------------------------------- #
#  Client HTTP (stdlib) — API compatible OpenAI de LM Studio
# --------------------------------------------------------------------------- #
def call_llm_chat(
    base_url: str, model: str, system: str, user: str,
    temperature: float, timeout_s: float, response_format_mode: str = "json_schema",
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Appelle LM Studio /v1/chat/completions avec un format de sortie configurable.

    ``json_schema`` est le contrat nominal. ``json_object`` et ``none`` sont des replis
    possibles pour les runtimes/modèles qui refusent la compilation de grammaire — mais
    le support de ``json_object`` varie selon la version de LM Studio (rejeté en HTTP 400
    par certaines versions, cf. ``config.yaml → lmstudio.response_format_fallback``) ;
    ``none`` (aucun ``response_format``, JSON demandé uniquement par le prompt) est le
    repli le plus universellement accepté. Dans tous les cas, la validation taxonomique
    reste ensuite entièrement côté application (``map_llm_response``).
    """
    # Certains modèles (ex. Mistral 7B Instruct) ont un template de chat qui
    # n'accepte PAS le rôle "system" (« Only user and assistant roles are
    # supported »). On fusionne donc les consignes dans le message "user" :
    # universel, compatible avec ou sans support du rôle system.
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "user", "content": f"{system}\n\n{user}"},
        ],
        "stream": False,
        "temperature": temperature,
    }
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)
    if response_format_mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "verbatim_classification",
                "strict": False,
                "schema": LLM_OUTPUT_SCHEMA,
            },
        }
    elif response_format_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}
    elif response_format_mode != "none":
        raise ValueError(f"Format de sortie LM Studio inconnu : {response_format_mode!r}")
    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (URL locale)
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # serveur joignable mais erreur (ex. 500 grammaire)
        try:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:300]
        except Exception:
            detail = ""
        raise LMStudioError(
            f"LM Studio a renvoyé HTTP {exc.code} ({url}, format={response_format_mode})"
            f" : {detail}",
            status_code=exc.code,
            retryable=exc.code in _RETRYABLE_HTTP_STATUS,
            response_format_mode=response_format_mode,
        ) from exc
    except urllib.error.URLError as exc:
        raise LMStudioError(
            f"LM Studio injoignable ({url}, format={response_format_mode}) : {exc}",
            retryable=True, response_format_mode=response_format_mode,
        ) from exc
    except (TimeoutError, OSError) as exc:
        raise LMStudioError(
            f"LM Studio timeout/erreur réseau ({url}, format={response_format_mode}) : {exc}",
            retryable=True, response_format_mode=response_format_mode,
        ) from exc

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
        engine = cfg.get("lmstudio", {}) or {}
        taxonomy_path = engine.get("taxonomy") or cfg["paths"]["taxonomy"]
        self.taxonomy = Taxonomy.from_json(resolve_path(cfg, taxonomy_path))
        # Construit une seule fois (pas par verbatim) : cf. build_label_normalizer.
        self.label_normalizer = build_label_normalizer(self.taxonomy, cfg, engine_name="lmstudio")
        self.anonymizer = Anonymizer(cfg)
        self.cleaner = TextCleaner(cfg)
        self.batch_size = cfg["model"]["batch_size_inference"]
        self.sentiment_labels = cfg["sentiment"]["labels"]
        self.signal_thresholds = {
            "rupture": cfg["thresholds"]["signal_rupture"],
            "churn": cfg["thresholds"]["signal_churn"],
            "insatisfaction": cfg["thresholds"]["signal_insatisfaction"],
        }
        self.base_url = engine.get("base_url", "http://host.docker.internal:1234/v1")
        self.model = engine.get("model", "local-model")
        self.temperature = float(engine.get("temperature", 0.1))
        self.timeout_s = float(engine.get("timeout_s", 120))
        self.max_tokens = max(1, int(engine.get("max_tokens", 256)))
        self.fallback_theme = engine.get("fallback_theme", FALLBACK_THEME_DEFAULT)
        self.fallback_niv2 = engine.get("fallback_niv2", "")
        self.prompt_version = str(engine.get("prompt_version", PROMPT_VERSION_DEFAULT))
        if self.fallback_niv2 and not self.taxonomy.is_valid_pair(
                self.fallback_theme, self.fallback_niv2):
            raise ValueError(
                "Repli LM Studio invalide pour le référentiel chargé : "
                f"{self.fallback_theme!r} / {self.fallback_niv2!r}")
        # Les modèles locaux, notamment les VLM Qwen, sont sensibles aux rafales au
        # chargement. Le défaut sûr est séquentiel ; l'exploitant peut l'augmenter après
        # une mesure réelle de stabilité/latence.
        self.max_parallel = max(1, int(engine.get("max_parallel", 1)))
        self.retries = max(0, int(engine.get("retries", 2)))
        self.retry_backoff_s = max(0.0, float(engine.get("retry_backoff_s", 2.0)))
        self.retry_backoff_max_s = max(
            self.retry_backoff_s, float(engine.get("retry_backoff_max_s", 12.0)))
        self.response_format_mode = str(engine.get("response_format", "json_schema"))
        self.response_format_fallback = str(engine.get("response_format_fallback", "json_object"))
        if self.response_format_mode not in ("json_schema", "json_object", "none"):
            raise ValueError(f"Format de sortie LM Studio invalide : {self.response_format_mode!r}")
        if self.response_format_fallback not in ("json_object", "none", ""):
            raise ValueError(
                "Format de repli LM Studio invalide : "
                f"{self.response_format_fallback!r}")
        self.warmup_enabled = bool(engine.get("warmup_enabled", True))
        self._warmup_done = False
        self._warmup_lock = threading.Lock()
        logger.info(
            "Moteur LM Studio : modèle=%s url=%s prompt=%s taxonomie=%s parallèle=%d "
            "format=%s max_tokens=%d warmup=%s",
            self.model, self.base_url, self.prompt_version, taxonomy_path, self.max_parallel,
            self.response_format_mode, self.max_tokens, self.warmup_enabled)

    def _retry_delay(self, attempt: int) -> float:
        """Backoff exponentiel court, avec jitter, pour laisser LM Studio finir son chargement."""
        if self.retry_backoff_s <= 0:
            return 0.0
        base = min(self.retry_backoff_max_s, self.retry_backoff_s * (2 ** attempt))
        return base + random.uniform(0.0, base * 0.25)

    def _call_raw_with_retries(self, system: str, user: str, *, purpose: str) -> Dict[str, Any]:
        """Appelle LM Studio sans mapper la réponse, avec retry temporisé et repli de format.

        Le repli (``none`` ou ``json_object``) ne s'active qu'après épuisement des essais
        du schéma et sur un statut compatible avec un refus de grammaire. Il ne contourne
        jamais la validation taxonomique exécutée ensuite par ``map_llm_response``.

        ``""`` (chaîne vide) est la seule valeur qui désactive le repli : ``"none"`` est un
        MODE de repli à part entière (aucun ``response_format`` envoyé), pas un synonyme de
        « pas de repli ». Les confondre désactiverait silencieusement le filet de sécurité
        dès que ``"none"`` est configuré — cf. recette_v4.py (« repli 'none' contrôlé »).
        """
        modes = [self.response_format_mode]
        if (self.response_format_mode == "json_schema"
                and self.response_format_fallback not in ("", "json_schema")):
            modes.append(self.response_format_fallback)

        last_exc: Optional[LMStudioError] = None
        for mode_index, mode in enumerate(modes):
            for attempt in range(self.retries + 1):
                try:
                    return call_llm_chat(
                        self.base_url, self.model, system, user, self.temperature,
                        self.timeout_s, response_format_mode=mode, max_tokens=self.max_tokens)
                except LMStudioError as exc:
                    last_exc = exc
                    if exc.retryable and attempt < self.retries:
                        delay = self._retry_delay(attempt)
                        logger.warning(
                            "LM Studio %s échoué (modèle=%s format=%s tentative=%d/%d, "
                            "retry dans %.1fs) : %s",
                            purpose, self.model, mode, attempt + 1, self.retries + 1, delay, exc)
                        if delay:
                            time.sleep(delay)
                        continue
                    break

            if (mode_index == 0 and len(modes) > 1 and last_exc is not None
                    and last_exc.status_code in _SCHEMA_FALLBACK_HTTP_STATUS):
                logger.warning(
                    "LM Studio refuse durablement le schéma (modèle=%s HTTP=%s) ; "
                    "repli contrôlé vers format=%s pour %s.",
                    self.model, last_exc.status_code, modes[1], purpose)
                continue
            break

        if last_exc is None:  # pragma: no cover - protection défensive
            raise LMStudioError("Échec LM Studio sans détail exploitable.")
        raise LMStudioError(
            "LM Studio indisponible après les essais configurés "
            f"(modèle={self.model}, format={last_exc.response_format_mode}, "
            f"HTTP={last_exc.status_code or 'réseau'}). Vérifiez le chargement du modèle, "
            "désactivez le chargement à la demande et gardez LMSTUDIO_MAX_PARALLEL=1. "
            f"Dernier détail : {last_exc}",
            status_code=last_exc.status_code,
            retryable=last_exc.retryable,
            response_format_mode=last_exc.response_format_mode,
        ) from last_exc

    def _ensure_warmup(self) -> None:
        """Déclenche une requête technique séquentielle avant la première rafale du lot."""
        if not self.warmup_enabled or self._warmup_done:
            return
        with self._warmup_lock:
            if self._warmup_done:
                return
            logger.info("Échauffement LM Studio avant traitement du lot (modèle=%s).", self.model)
            self._call_raw_with_retries(_WARMUP_SYSTEM, _WARMUP_USER, purpose="échauffement")
            self._warmup_done = True

    def _call_with_retries(self, prompt: Dict[str, str], cleaned_text: str,
                           satisfaction: Optional[float]) -> Dict[str, Any]:
        """Appelle le LLM avec retries puis revalide -> sortie OUTPUT_COLUMNS.

        Une erreur de connexion persistante (après ``retries``) lève LMStudioError :
        elle remonte jusqu'à la tâche worker qui marque le lot 'failed' (échec propre).
        Une réponse JSON malformée n'est PAS une LMStudioError (gérée par le repli).
        """
        raw = self._call_raw_with_retries(prompt["system"], prompt["user"], purpose="classification")
        return map_llm_response(
            raw, cleaned_text, satisfaction, self.taxonomy, self.cfg,
            self.sentiment_labels, engine_name="lmstudio",
            label_normalizer=self.label_normalizer)

    def _predict_one(self, cleaned_text: str, satisfaction: Optional[float]) -> Dict[str, Any]:
        """Prédit un verbatim (mode proposeur), avec retries sur erreur transitoire."""
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_llm_prompt(
            self.taxonomy, cleaned_text, satisfaction, self.fallback_theme,
            self.prompt_version, getattr(self, "fallback_niv2", ""))
        return self._call_with_retries(prompt, cleaned_text, satisfaction)

    def _refine_one(self, cleaned_text: str, satisfaction: Optional[float],
                    proposal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Raffine un verbatim (mode raffineur) à partir de la proposition du moteur 1."""
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_refiner_prompt(
            self.taxonomy, cleaned_text, proposal, satisfaction,
            self.fallback_theme, self.prompt_version,
            getattr(self, "fallback_niv2", ""))
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
        if cleaned:
            self._ensure_warmup()
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
        if n:
            self._ensure_warmup()
        return self._run_pool(n,
                              lambda i: self._refine_one(cleaned[i], satisfactions[i], proposals[i]))
