"""Moteur de classification « Claude » (API Anthropic) — V5.

Quatrième backend de prédiction. **COMPARAISON / TEST UNIQUEMENT** : Claude n'est
JAMAIS sélectionnable pour un run de production (refus côté serveur à l'activation
et au démarrage de job). cf. docs/SPEC_V5_MULTI_MOTEUR §0 (V5-D1) et §5.

Expose la même interface que les autres moteurs (`anonymizer`, `cleaner`,
`batch_size`, `signal_thresholds`, `sentiment_labels`, `predict_cleaned_batch`)
plus, comme tout moteur LLM, le mode raffineur (`refine_cleaned_batch`).

Principes :
  - **Client natif Anthropic** : ``POST {base_url}/v1/messages`` (format Messages),
    sortie **structurée par tool use** (outil à ``input_schema`` imposé +
    ``tool_choice`` forcé) — mécanisme distinct du ``response_format`` de LM Studio,
    mais **forme de sortie + revalidation taxonomie identiques** (mutualisées via
    ``llm_common``). Aucun routage par LM Studio (V5-D15).
  - Transport en **stdlib** (``urllib``) — cohérent avec le moteur LM Studio de
    référence (V4-D10), zéro dépendance ajoutée, recette torch-free et sans dépendance.
  - Le texte transmis est **déjà anonymisé + nettoyé** (étapes amont inchangées) :
    l'unique flux sortant possible est worker → ``api.anthropic.com``, et seulement
    lors d'un test/comparaison.
  - **Secret** : ``ANTHROPIC_API_KEY`` lue depuis l'environnement UNIQUEMENT
    (jamais en base, jamais en config, jamais en UI — V5-D2).
  - Sortie revalidée par ``map_llm_response`` (taxo + repli + garde-fous V4).
  - **Échec propre** : timeouts/retries puis ``ClaudeError`` (pas de repli silencieux).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.preprocessing import Anonymizer, TextCleaner
from src.utils import Taxonomy, resolve_path

from .llm_common import (
    FALLBACK_THEME_DEFAULT,
    LLM_OUTPUT_SCHEMA,
    PROMPT_VERSION_DEFAULT,
    build_llm_prompt,
    build_refiner_prompt,
    empty_output,
    map_llm_response,
)

logger = logging.getLogger("worker.claude")

ANTHROPIC_VERSION = "2023-06-01"
CLASSIFY_TOOL_NAME = "classer_verbatim"
JUDGE_TOOL_NAME = "rendre_verdict"

# Schéma de sortie du juge (V5-D9/D11) : pairwise aveuglé -> A / B / égalité + justification.
JUDGE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "tie"]},
        "rationale": {"type": "string"},
    },
    "required": ["winner", "rationale"],
}


class ClaudeError(RuntimeError):
    """Échec d'appel à l'API Anthropic (réseau, HTTP, timeout, clé absente). Fait échouer le run."""


# --------------------------------------------------------------------------- #
#  Client HTTP (stdlib) — API Messages d'Anthropic, sortie structurée tool use
# --------------------------------------------------------------------------- #
def call_claude_messages(
    base_url: str, api_key: str, model: str, system: str, user: str,
    max_tokens: int, timeout_s: float,
    tool_name: str = CLASSIFY_TOOL_NAME, input_schema: Optional[Dict[str, Any]] = None,
    tool_description: str = "Renvoie la classification du verbatim, strictement dans la taxonomie imposée.",
) -> Dict[str, Any]:
    """Appelle ``/v1/messages`` en sortie structurée (tool use forcé). Lève ClaudeError sur échec.

    La sortie est contrainte par un outil (``tool_name`` + ``input_schema``) et
    ``tool_choice`` forcé ; on lit le bloc ``tool_use`` correspondant. Par défaut, outil
    de **classification** (schéma LLM_OUTPUT_SCHEMA, revalidé ensuite par map_llm_response) ;
    le **juge** (C5) passe ``tool_name=JUDGE_TOOL_NAME`` + ``input_schema=JUDGE_OUTPUT_SCHEMA``.
    Si aucun bloc exploitable, renvoie {}.
    NB : ``temperature``/``top_p`` ne sont PAS envoyés (rejetés par Opus 4.7+/Fable).
    """
    if not api_key:
        raise ClaudeError("ANTHROPIC_API_KEY absente : moteur Claude indisponible.")
    tool = {
        "name": tool_name,
        "description": tool_description,
        "input_schema": input_schema or LLM_OUTPUT_SCHEMA,
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    url = base_url.rstrip("/") + "/v1/messages"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:        # joignable mais erreur (4xx/5xx)
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        raise ClaudeError(f"Anthropic a renvoyé HTTP {exc.code} ({url}) : {detail}") from exc
    except urllib.error.URLError as exc:
        raise ClaudeError(f"Anthropic injoignable ({url}) : {exc}") from exc
    except (TimeoutError, OSError) as exc:
        raise ClaudeError(f"Anthropic timeout/erreur réseau ({url}) : {exc}") from exc

    content = body.get("content", []) if isinstance(body, dict) else []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == tool_name:
            inp = block.get("input")
            return inp if isinstance(inp, dict) else {}
    # Pas de tool_use exploitable (cas rare) : le mapping appliquera le repli.
    logger.warning("Réponse Anthropic sans bloc tool_use exploitable.")
    return {}


def build_judge_prompt(verbatim: str, classif_a: str, classif_b: str) -> Dict[str, str]:
    """Prompt du juge **aveuglé** (V5-D11) : deux classifications « A » / « B » anonymes.

    Aucun nom de moteur n'apparaît : le juge ne sait pas qui a produit A ou B (et l'ordre
    A/B est permuté côté worker). Pairwise, sans vérité terrain (V5-D9).
    """
    system = (
        "Tu es un évaluateur expert de la classification de verbatims clients e-commerce "
        "(enseigne Cultura). On te présente un verbatim et DEUX classifications anonymes, "
        "« A » et « B », produites par deux systèmes que tu ne connais pas. Choisis la "
        "classification la PLUS PERTINENTE au regard du verbatim (grand thème, sous-thème, "
        "sentiment), ou « tie » si elles se valent. Tu réponds UNIQUEMENT via l'outil, avec "
        "une justification courte et factuelle (sans nommer A/B comme un système)."
    )
    user = (
        f"Verbatim :\n\"\"\"\n{verbatim}\n\"\"\"\n\n"
        f"Classification A : {classif_a}\n"
        f"Classification B : {classif_b}\n\n"
        "Quelle classification est la plus pertinente ? Réponds par A, B ou tie."
    )
    return {"system": system, "user": user}


# --------------------------------------------------------------------------- #
#  Prédicteur (orchestration)
# --------------------------------------------------------------------------- #
class ClaudePredictor:
    """Backend Claude (API Anthropic) — COMPARAISON/TEST uniquement (jamais en prod)."""

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
        engine = cfg.get("claude", {}) or {}
        self.base_url = engine.get("base_url", "https://api.anthropic.com")
        self.model = engine.get("model", "claude-opus-4-8")
        self.timeout_s = float(engine.get("timeout_s", 60))
        self.max_tokens = int(engine.get("max_tokens", 1024))
        self.fallback_theme = engine.get("fallback_theme", FALLBACK_THEME_DEFAULT)
        self.prompt_version = str(engine.get("prompt_version", PROMPT_VERSION_DEFAULT))
        self.max_parallel = max(1, int(engine.get("max_parallel", 4)))
        self.retries = max(0, int(engine.get("retries", 2)))
        # Secret lu depuis l'ENV uniquement (jamais cfg/base/UI).
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        logger.info("Moteur Claude (comparaison) : modèle=%s url=%s prompt=%s parallèle=%d clé=%s",
                    self.model, self.base_url, self.prompt_version, self.max_parallel,
                    "présente" if self.api_key else "ABSENTE")

    def _call_with_retries(self, prompt: Dict[str, str], cleaned_text: str,
                           satisfaction: Optional[float]) -> Dict[str, Any]:
        """Appelle Claude avec retries puis revalide -> sortie OUTPUT_COLUMNS. Échec propre."""
        last_exc: Optional[ClaudeError] = None
        for attempt in range(self.retries + 1):
            try:
                raw = call_claude_messages(
                    self.base_url, self.api_key, self.model, prompt["system"], prompt["user"],
                    self.max_tokens, self.timeout_s)
                return map_llm_response(
                    raw, cleaned_text, satisfaction, self.taxonomy, self.cfg, self.sentiment_labels)
            except ClaudeError as exc:
                last_exc = exc
                if attempt < self.retries:
                    logger.warning("Appel Claude échoué (tentative %d/%d) : %s",
                                   attempt + 1, self.retries + 1, exc)
        raise last_exc  # type: ignore[misc]

    def _predict_one(self, cleaned_text: str, satisfaction: Optional[float]) -> Dict[str, Any]:
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_llm_prompt(
            self.taxonomy, cleaned_text, satisfaction, self.fallback_theme, self.prompt_version)
        return self._call_with_retries(prompt, cleaned_text, satisfaction)

    def _refine_one(self, cleaned_text: str, satisfaction: Optional[float],
                    proposal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not cleaned_text or cleaned_text.strip() == "":
            return empty_output(cleaned_text)
        prompt = build_refiner_prompt(
            self.taxonomy, cleaned_text, proposal, satisfaction,
            self.fallback_theme, self.prompt_version)
        return self._call_with_retries(prompt, cleaned_text, satisfaction)

    def _run_pool(self, n: int, submit) -> List[Dict[str, Any]]:
        """Pool borné (``max_parallel``), ordre préservé, fail-fast sur ClaudeError."""
        results: List[Optional[Dict[str, Any]]] = [None] * n
        if n == 0:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_parallel, n)) as executor:
            futures = {executor.submit(submit, i): i for i in range(n)}
            try:
                for fut in as_completed(futures):
                    results[futures[fut]] = fut.result()
            except ClaudeError:
                for f in futures:
                    f.cancel()
                raise
        return results  # type: ignore[return-value]

    def predict_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[list] = None,
    ) -> List[Dict[str, Any]]:
        """Prédit à partir de textes DÉJÀ anonymisés + nettoyés (mode proposeur)."""
        if satisfactions is None:
            satisfactions = [None] * len(cleaned)
        return self._run_pool(len(cleaned),
                              lambda i: self._predict_one(cleaned[i], satisfactions[i]))

    def refine_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[list],
        proposals: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Raffine des prédictions (cascade V5) à partir de textes DÉJÀ anonymisés.

        Même contrat que ``LMStudioPredictor.refine_cleaned_batch`` (SPEC_V5 §4.1).
        NB : Claude est exclu de la cascade de PRODUCTION ; ce mode sert la
        comparaison/test où Claude joue le rôle de raffineur de référence.
        """
        n = len(cleaned)
        if satisfactions is None:
            satisfactions = [None] * n
        return self._run_pool(n,
                              lambda i: self._refine_one(cleaned[i], satisfactions[i], proposals[i]))

    def judge_pairwise(self, verbatim: str, classif_a: str, classif_b: str) -> Dict[str, Any]:
        """Juge Claude (C5) : tranche entre les classifications A et B (aveuglé).

        Renvoie {"winner": "A"|"B"|"tie", "rationale": str}. L'aveuglement et la
        permutation A/B sont gérés par l'appelant (worker) ; ici on ne fait que juger.
        Échec propre (ClaudeError) après retries ; réponse hors-forme -> "tie" (neutre).
        """
        prompt = build_judge_prompt(verbatim, classif_a, classif_b)
        last_exc: Optional[ClaudeError] = None
        for attempt in range(self.retries + 1):
            try:
                raw = call_claude_messages(
                    self.base_url, self.api_key, self.model, prompt["system"], prompt["user"],
                    self.max_tokens, self.timeout_s,
                    tool_name=JUDGE_TOOL_NAME, input_schema=JUDGE_OUTPUT_SCHEMA,
                    tool_description="Rends un verdict pairwise entre les classifications A et B.")
                winner = raw.get("winner") if isinstance(raw, dict) else None
                if winner not in ("A", "B", "tie"):
                    winner = "tie"
                rationale = str(raw.get("rationale", "") if isinstance(raw, dict) else "")[:1000]
                return {"winner": winner, "rationale": rationale}
            except ClaudeError as exc:
                last_exc = exc
                if attempt < self.retries:
                    logger.warning("Appel juge Claude échoué (tentative %d/%d) : %s",
                                   attempt + 1, self.retries + 1, exc)
        raise last_exc  # type: ignore[misc]
