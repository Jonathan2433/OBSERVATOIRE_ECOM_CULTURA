"""Feature engineering textuel partagé entre entraînement et inférence.

``sentiment_input`` formate l'entrée du modèle de sentiment en injectant
(optionnellement) le score de satisfaction sous forme de PRÉFIXE textuel
normalisé. Ce signal auxiliaire est fortement corrélé au sentiment.

Choix : préfixe textuel plutôt que concaténation à l'embedding [CLS]. La
concaténation imposerait une tête custom, incompatible avec l'export ONNX
standard d'optimum (contrainte CPU du POC). Le préfixe exploite le même signal
tout en conservant une architecture HuggingFace standard.

IMPORTANT : cette fonction DOIT être appelée de manière identique à
l'entraînement (train_sentiment) et à l'inférence (predictor), sinon les
distributions divergent.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


#: Borne haute de l'échelle par défaut. Les modèles actifs (juin 2026) ont été
#: entraînés sur une échelle 1-10 ; la livraison Cultura du 09/09 est sur 1-4.
DEFAULT_SCALE_MAX = 10


def echelle_max(cfg: Dict[str, Any]) -> int:
    """Borne haute de l'échelle de satisfaction, lue en configuration (ENF-8)."""
    return int(cfg.get("sentiment", {}).get("satisfaction_scale_max", DEFAULT_SCALE_MAX))


def sentiment_input(text: str, satisfaction: Optional[float], cfg: Dict[str, Any]) -> str:
    """Construit l'entrée du modèle de sentiment (préfixe satisfaction optionnel).

    ⚠️ **La borne de l'échelle fait partie du contrat du modèle.** Elle était
    codée en dur à 10, alors que la livraison Cultura du 09/09 est sur 1-4
    (D-20, §7.2 de SPEC_CHARGEUR). Présenter une note 1-4 à un modèle entraîné
    sur 1-10 est un piège silencieux : un client **très satisfait (4/4)**
    deviendrait ``[SATISFACTION 4/10]``, que l'entraînement associe à
    l'insatisfaction. La baseline en sortirait artificiellement mauvaise, et le
    gain du nouveau modèle artificiellement bon.

    La valeur doit donc **suivre le modèle chargé**, jamais les données : elle
    est inscrite dans ``training_card.json`` à l'entraînement et contrôlée par
    :func:`verifier_echelle` au chargement.
    """
    text = "" if text is None else str(text)
    if not politique_prefixe(cfg)["actif"]:
        return text
    if not _prefixe_applicable(text, cfg):
        return text
    score = _valid_score(satisfaction, echelle_max(cfg))
    if score is None:
        return text
    return f"[SATISFACTION {score}/{echelle_max(cfg)}] {text}"


def politique_prefixe(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Politique de préfixe en vigueur, sous forme sérialisable.

    Inscrite telle quelle dans ``training_card.json`` à l'entraînement, et
    comparée à la configuration au chargement du modèle.
    """
    sent = cfg.get("sentiment", {}) or {}
    cond = sent.get("prefixe_conditionnel", {}) or {}
    return {
        "actif": bool(sent.get("use_satisfaction_prefix", True)),
        "echelle_max": echelle_max(cfg),
        "conditionnel": bool(cond.get("actif", False)),
        "max_mots": int(cond.get("max_mots", 0)) if cond.get("actif", False) else None,
    }


def _prefixe_applicable(text: str, cfg: Dict[str, Any]) -> bool:
    """D-39 — le préfixe n'est appliqué qu'aux verbatims courts.

    Mesuré sur la baseline : la note de satisfaction apporte +0,418 d'accuracy
    sur les verbatims de 1-2 mots, où le texte ne porte aucun signal, mais lui
    en retire 0,157 au-delà de 20 mots, où elle écrase un contenu nuancé.
    """
    pol = politique_prefixe(cfg)
    if not pol["conditionnel"]:
        return True
    return len([t for t in str(text).split() if t]) <= pol["max_mots"]


def verifier_politique_prefixe(cfg: Dict[str, Any],
                               training_card: Dict[str, Any]) -> None:
    """Échoue si la politique de préfixe diffère de celle de l'entraînement.

    Garde-fou de l'invariant « préparation identique à l'entraînement et à
    l'inférence », que le module signale en capitales depuis l'origine sans
    qu'aucun contrôle ne l'ait jamais appliqué. Une carte d'entraînement
    antérieure à ce contrôle ne porte pas la politique : elle est tolérée.
    """
    attendue = training_card.get("politique_prefixe")
    if attendue is None:
        # Compatibilité ascendante : les cartes de juin 2026 ne portent que
        # l'échelle, et encore, implicitement.
        return verifier_echelle(cfg, training_card)
    courante = politique_prefixe(cfg)
    if attendue != courante:
        raise ValueError(
            f"Politique de préfixe incohérente entre le modèle et la "
            f"configuration.\n  entraînement : {attendue}\n  configuration : "
            f"{courante}\nLe modèle ne verrait pas la même entrée qu'à "
            f"l'entraînement — aligner la section `sentiment` de config.yaml."
        )


def verifier_echelle(cfg: Dict[str, Any], training_card: Dict[str, Any]) -> None:
    """Échoue si l'échelle de la configuration diffère de celle de l'entraînement."""
    attendue = training_card.get("satisfaction_scale_max")
    if attendue is None:
        return
    courante = echelle_max(cfg)
    if int(attendue) != courante:
        raise ValueError(
            f"Échelle de satisfaction incohérente : le modèle a été entraîné sur "
            f"1-{attendue}, la configuration annonce 1-{courante}. Le préfixe "
            f"`[SATISFACTION x/{courante}]` ne correspondrait pas à ce que le "
            f"modèle a vu — corriger `sentiment.satisfaction_scale_max`."
        )


def _valid_score(value: Any, scale_max: int = DEFAULT_SCALE_MAX) -> Optional[int]:
    """Renvoie un score entier 1..scale_max valide, sinon None."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        score = int(round(float(value)))
    except (ValueError, TypeError):
        return None
    if 1 <= score <= scale_max:
        return score
    return None
