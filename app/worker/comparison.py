"""Comparaison objective de moteurs (V5, lot C4) — logique PURE (sans I/O, sans juge).

Le run lui-même (orchestration RQ, replay des prédicteurs, persistance) vit dans
``tasks.run_comparison_job`` ; ce module ne contient que :
  - l'échantillonnage **reproductible** (graine) ;
  - les **métriques objectives** : taux d'accord inter-moteurs sur ``theme1_niv1``,
    distribution de confiance, latence/coût par moteur, distribution de sentiment.

Le **juge Claude** (win-rate, exemples commentés) est ajouté au lot C5 ; sans lui,
la comparaison reste pleinement utile (mode dégradé). cf. SPEC_V5 §7.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple

DEFAULT_SAMPLE_SIZE = 50
MAX_SAMPLE_SIZE = 200


def clamp_sample_size(requested: int, default: int = DEFAULT_SAMPLE_SIZE,
                      maximum: int = MAX_SAMPLE_SIZE) -> int:
    """Borne la taille d'échantillon : défaut si <=0, plafonnée à ``maximum`` (V5-D10)."""
    try:
        n = int(requested)
    except (TypeError, ValueError):
        n = default
    if n <= 0:
        n = default
    return min(n, maximum)


def sample_indices(population: int, sample_size: int, seed: int) -> List[int]:
    """Indices [0, population) tirés de façon **reproductible** (même graine -> même tirage).

    Retourne tous les indices (triés) si l'échantillon demandé couvre la population.
    """
    n = min(clamp_sample_size(sample_size), population)
    if n >= population:
        return list(range(population))
    rng = random.Random(seed)
    return sorted(rng.sample(range(population), n))


def agreement_matrix(theme_by_engine: Dict[str, Sequence[str]]) -> Dict[str, float]:
    """Taux d'accord inter-moteurs sur ``theme1_niv1`` (objectif, sans juge).

    Entrée : {libellé_moteur: [theme1_niv1 pour chaque verbatim de l'échantillon]}.
    Sortie : {"A vs B": part d'accord ∈ [0,1]} pour chaque paire.
    """
    engines = list(theme_by_engine)
    out: Dict[str, float] = {}
    for i, a in enumerate(engines):
        for b in engines[i + 1:]:
            ta, tb = theme_by_engine[a], theme_by_engine[b]
            n = min(len(ta), len(tb))
            if not n:
                out[f"{a} vs {b}"] = 0.0
                continue
            agree = sum(1 for k in range(n) if (ta[k] or "") == (tb[k] or ""))
            out[f"{a} vs {b}"] = round(agree / n, 4)
    return out


def confidence_summary(conf_by_engine: Dict[str, Sequence[float]]) -> Dict[str, Dict[str, float]]:
    """Statistiques de confiance par moteur : moyenne / min / max / n (valeurs valides)."""
    out: Dict[str, Dict[str, float]] = {}
    for engine, confs in conf_by_engine.items():
        vals = [float(c) for c in confs if isinstance(c, (int, float))]
        out[engine] = {
            "moyenne": round(sum(vals) / len(vals), 4) if vals else 0.0,
            "min": round(min(vals), 4) if vals else 0.0,
            "max": round(max(vals), 4) if vals else 0.0,
            "n": len(vals),
        }
    return out


def latency_summary(latency_ms_by_engine: Dict[str, float]) -> Dict[str, float]:
    """Latence moyenne par verbatim (ms) par moteur — arrondie."""
    return {engine: round(float(ms), 2) for engine, ms in latency_ms_by_engine.items()}


def sentiment_distribution(sent_by_engine: Dict[str, Sequence[str]]) -> Dict[str, Dict[str, int]]:
    """Volumétrie de sentiment par moteur (pour l'affichage empilé)."""
    out: Dict[str, Dict[str, int]] = {}
    for engine, sents in sent_by_engine.items():
        d = {"Négatif": 0, "Neutre": 0, "Positif": 0}
        for s in sents:
            if s in d:
                d[s] += 1
        out[engine] = d
    return out


def divergent_indices(theme_by_engine: Dict[str, Sequence[str]]) -> List[int]:
    """Indices de l'échantillon où **au moins deux moteurs divergent** sur ``theme1_niv1``.

    Sert au juge (C5) : on ne fait juger que les divergences. Calculé dès C4 pour la
    métrique « nb de divergences » et pour préparer C5.
    """
    engines = list(theme_by_engine)
    if len(engines) < 2:
        return []
    n = min(len(theme_by_engine[e]) for e in engines)
    out = []
    for k in range(n):
        labels = {(theme_by_engine[e][k] or "") for e in engines}
        if len(labels) > 1:
            out.append(k)
    return out


def build_metrics(
    theme_by_engine: Dict[str, Sequence[str]],
    conf_by_engine: Dict[str, Sequence[float]],
    sent_by_engine: Dict[str, Sequence[str]],
    latency_ms_by_engine: Dict[str, float],
    sample_size: int,
) -> Dict[str, Any]:
    """Agrège toutes les métriques objectives d'un run en un dict JSON-sérialisable."""
    div = divergent_indices(theme_by_engine)
    return {
        "engines": list(theme_by_engine),
        "sample_size": int(sample_size),
        "agreement": agreement_matrix(theme_by_engine),
        "confidence": confidence_summary(conf_by_engine),
        "latency_ms": latency_summary(latency_ms_by_engine),
        "sentiment": sentiment_distribution(sent_by_engine),
        "n_divergences": len(div),
        "judge": None,   # rempli au lot C5 (win-rate + exemples) ; None = mode dégradé
    }
