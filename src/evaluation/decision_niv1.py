"""Décision multi-label de niveau 1, isolée et pure — lot L2.

Pourquoi ce module existe
-------------------------
``src/evaluation/evaluate.py`` calcule le F1 de niveau 1 sur
``niv1_probs >= seuil``, **sans appliquer le plafond ``max_themes``**. Il évalue
donc une décision que le produit ne prend jamais : en production,
``build_output`` tronque à 2 thèmes.

Conséquence mesurée sur le prototype : rappel micro 0,830 et F1-micro 0,479, soit
une **précision micro implicite de 0,336** — environ 2,5 thèmes activés par
verbatim au seuil de 0,35. La sur-activation était invisible dans le rapport
d'évaluation, alors qu'elle est le cœur du grief métier n°1 : un second thème
parasite crée du volume fictif et fausse la priorisation des chantiers.

Où vit la décision
------------------
La décision réelle du produit vit dans ``src/inference/decision.py``
(``PolitiqueDecision``), **une seule fois**, et ``build_output`` l'appelle. Ce
module-ci ne la redéfinit plus : il fournit

* la **décision de base** — seuil unique, repli sur l'argmax, plafond — qui reste
  utile pour balayer un seuil (courbe L5') indépendamment des leviers ;
* les **mesures** de qualité du second thème, calculables sur *n'importe quelle*
  décision, qu'elle vienne de la politique complète ou du seuil nu.

Les mesures prennent donc en entrée une décision déjà prise (``decisions`` :
une liste d'indices par verbatim). C'est ce qui garantit qu'on évalue le produit
et non une approximation : depuis que les leviers de la couche de décision
déplacent le **thème 1** lui-même, une réimplémentation « fidèle à la main »
mesurerait un produit qui n'existe pas.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np


def themes_decides(niv1_probs: np.ndarray, seuil: float, max_themes: int) -> List[int]:
    """Indices des thèmes réellement retenus pour UN verbatim, par proba décroissante.

    Reproduit ``build_output`` étape 1 :

    1. activés = ``{i : p_i >= seuil}``, triés par probabilité décroissante ;
    2. si aucun ne passe le seuil, repli sur l'argmax — **au moins un thème est
       toujours retourné** ;
    3. troncature à ``max_themes``.
    """
    probs = np.asarray(niv1_probs, dtype=float)
    ordre = np.argsort(-probs)
    actives = [int(i) for i in ordre if probs[i] >= seuil]
    if not actives:
        actives = [int(ordre[0])]
    return actives[:max_themes]


def matrice_decidee(niv1_probs: np.ndarray, seuil: float, max_themes: int) -> np.ndarray:
    """Matrice binaire (n, n_themes) de la décision réelle, plafond compris."""
    probs = np.asarray(niv1_probs, dtype=float)
    y = np.zeros_like(probs, dtype=int)
    for ligne in range(probs.shape[0]):
        for idx in themes_decides(probs[ligne], seuil, max_themes):
            y[ligne, idx] = 1
    return y


def distribution_nb_themes(y_decide: np.ndarray) -> Dict[str, Any]:
    """Distribution du nombre de thèmes émis (EF-4).

    À comparer à la distribution annotée : la référence de départ mesurée est de
    **43,3 % de sorties bi-thèmes contre 0,4 % d'annotations bi-thèmes** sur le
    prototype, et 4,4 % d'annotations bi-thèmes sur le corpus Cultura.
    """
    compte = y_decide.sum(axis=1)
    n = max(len(compte), 1)
    return {
        "n": int(len(compte)),
        "moyenne_themes_par_verbatim": round(float(compte.mean()), 4) if len(compte) else 0.0,
        "part_mono_theme": round(float((compte == 1).sum()) / n, 4),
        "part_bi_theme": round(float((compte >= 2).sum()) / n, 4),
    }


def decisions_de_base(niv1_probs: np.ndarray, seuil: float,
                      max_themes: int) -> List[List[int]]:
    """Décision de base pour tout un lot : ``[themes_decides(p) for p in probs]``."""
    probs = np.asarray(niv1_probs, dtype=float)
    return [themes_decides(probs[i], seuil, max_themes) for i in range(probs.shape[0])]


def matrice_depuis_decisions(decisions: Sequence[Sequence[int]],
                             n_themes: int) -> np.ndarray:
    """Matrice binaire (n, n_themes) à partir d'une décision déjà prise."""
    y = np.zeros((len(decisions), n_themes), dtype=int)
    for ligne, indices in enumerate(decisions):
        for idx in indices:
            y[ligne, idx] = 1
    return y


def mesures_second_theme(y_vrai: np.ndarray,
                         decisions: Sequence[Sequence[int]]) -> Dict[str, Any]:
    """Qualité du **second** thème à partir de la décision réellement prise.

    - ``precision_second_theme`` : parmi les verbatims où un second thème est
      remonté, la part où il est effectivement annoté.
    - ``taux_faux_second_theme`` : parmi les verbatims réellement **mono**-thème,
      la part où un second thème est tout de même remonté.
    - ``rappel_second_theme`` : parmi les verbatims réellement **bi**-thèmes, la
      part où un second thème est remonté et juste.

    Les cibles associées ont changé le 11/09/2026 : la précision du second thème
    devient un **indicateur suivi**, et l'engagement porte sur le taux de faux
    second thème (≤ 10 %). Cf. docs/OPTIMISATION_SANS_CULTURA.md §4.
    """
    y_vrai = np.asarray(y_vrai, dtype=int)
    if len(decisions) != y_vrai.shape[0]:
        raise ValueError(
            f"Décision et vérité de tailles différentes : {len(decisions)} "
            f"contre {y_vrai.shape[0]}. Une mesure sur deux populations "
            "distinctes ne veut rien dire.")

    seconds_justes = seconds_emis = 0
    mono_vrais = mono_avec_faux_second = 0
    bi_vrais = bi_rattrapes = 0

    for ligne, decides in enumerate(decisions):
        vrais = set(np.flatnonzero(y_vrai[ligne]).tolist())
        if len(decides) >= 2:
            seconds_emis += 1
            if decides[1] in vrais:
                seconds_justes += 1
        if len(vrais) <= 1:
            mono_vrais += 1
            if len(decides) >= 2:
                mono_avec_faux_second += 1
        else:
            bi_vrais += 1
            if len(decides) >= 2 and decides[1] in vrais:
                bi_rattrapes += 1

    def ratio(a: int, b: int):
        return round(a / b, 4) if b else None

    return {
        "seconds_themes_emis": seconds_emis,
        "precision_second_theme": ratio(seconds_justes, seconds_emis),
        "verbatims_mono_theme_annotes": mono_vrais,
        "taux_faux_second_theme": ratio(mono_avec_faux_second, mono_vrais),
        "verbatims_bi_themes_annotes": bi_vrais,
        "rappel_second_theme": ratio(bi_rattrapes, bi_vrais),
    }


def precision_second_theme(y_vrai: np.ndarray, niv1_probs: np.ndarray,
                           seuil: float, max_themes: int) -> Dict[str, Any]:
    """Qualité du second thème **sous la décision de base** (seuil nu).

    Conservée pour la courbe de seuil et les recettes. Pour mesurer le produit
    tel qu'il décide réellement, passer par :func:`mesures_second_theme` avec la
    décision issue de ``PolitiqueDecision``.
    """
    return mesures_second_theme(y_vrai, decisions_de_base(niv1_probs, seuil, max_themes))


def courbe_seuil(y_vrai: np.ndarray,
                 niv1_probs: np.ndarray,
                 seuils: Sequence[float],
                 max_themes: int) -> List[Dict[str, Any]]:
    """Courbe seuil → qualité du second thème — livrable du lot L5'.

    Pour chaque seuil, rejoue la décision complète (seuil, repli sur l'argmax,
    plafond) et retourne les trois grandeurs qui arbitrent le réglage :

    * **précision du second thème** — cible ≥ 0,70 *(à valider, Q-9)* ;
    * **taux de faux second thème** sur les verbatims réellement mono-thème —
      cible ≤ 15 % ;
    * **rappel du second thème** sur les verbatims réellement bi-thèmes.

    Le seuil retenu est un arbitrage métier, pas un optimum mathématique : un
    second thème parasite crée du volume fictif dans les tableaux de priorisation
    de Cultura, un second thème manquant en retire. Les deux faussent une
    décision d'investissement, et pas symétriquement.

    .. warning:: **À exécuter sur le jeu de validation du modèle concerné.** Les
       probabilités dépendent du modèle *et* de son espace de labels : un seuil
       calibré sur l'ancien modèle (référentiel 20/67) n'est pas transposable au
       nouveau (11/59). Le seuil opérationnel se fixe donc **après** le
       réentraînement, sur la validation — L5' livre l'outil et la méthode, L6
       produit la valeur.
    """
    lignes: List[Dict[str, Any]] = []
    for seuil in seuils:
        y = matrice_decidee(niv1_probs, seuil, max_themes)
        mesures = precision_second_theme(y_vrai, niv1_probs, seuil, max_themes)
        lignes.append({
            "seuil": round(float(seuil), 4),
            **distribution_nb_themes(y),
            **mesures,
        })
    return lignes


def seuils_par_defaut(debut: float = 0.20, fin: float = 0.90,
                      pas: float = 0.05) -> List[float]:
    """Grille de seuils par défaut pour :func:`courbe_seuil`."""
    n = int(round((fin - debut) / pas)) + 1
    return [round(debut + i * pas, 4) for i in range(n)]
