"""Split train / validation / test **par texte unique** — lot L2.

Pourquoi ce module existe
-------------------------
Le split historique (``prepare_dataset.py``) découpe des **indices de lignes**.
Sur un jeu où le même texte apparaît sur plusieurs lignes, cela met le même
verbatim des deux côtés de la barrière. Mesuré sur le prototype : **99,6 % des
lignes de test** avaient un texte strictement identique dans le train, ce qui
rend invalides *toutes* les métriques d'``eval_report.json`` — le F1-macro
niveau 2 de 0,891 mesurait de la mémorisation, pas de la généralisation.

Le corpus Cultura n'est pas à l'abri : **1 641 doublons de texte sur 8 236
occurrences (19,9 %)**, principalement des réponses très courtes répétées
(« nul », « aucun », « très bien »).

Principe
--------
1. Les lignes sont regroupées par **texte normalisé** (casse, espaces).
2. Ce sont les **groupes** qui sont répartis, jamais les lignes.
3. La stratification porte sur le thème de niveau 1 dominant du groupe.
4. Le contrôle d'absence de fuite est **bloquant** et intégré à la fonction de
   split : il ne peut pas être contourné en oubliant de l'appeler.
"""
from __future__ import annotations

import logging
import random
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

SPLITS = ("train", "val", "test")
#: Strate des verbatims sans annotation de thème (ils servent à l'inférence).
STRATE_NON_ANNOTE = "__NON_ANNOTE__"


class FuiteDetectee(RuntimeError):
    """Un même texte apparaît dans deux splits différents.

    Erreur bloquante : laisser passer une fuite produit des métriques flatteuses
    et fausses, et il n'existe aucun moyen de s'en apercevoir a posteriori sans
    refaire la mesure.
    """


def cle_texte(texte: object) -> str:
    """Clé de regroupement d'un verbatim.

    Volontairement **conservatrice** : casse, accents composés et espaces
    seulement. Une clé plus agressive (retrait de la ponctuation, racinisation)
    fusionnerait des verbatims réellement distincts et retirerait du signal ;
    une clé plus permissive (égalité stricte) laisserait passer « Très bien » /
    « très bien  », qui sont le même verbatim.
    """
    s = unicodedata.normalize("NFKC", str(texte)).casefold()
    return " ".join(s.split())


def _strate_du_groupe(labels: Sequence[object]) -> str:
    """Thème de niveau 1 dominant d'un groupe, ou strate « non annoté »."""
    valeurs = [str(v) for v in labels if v is not None and str(v) not in ("", "nan", "None")]
    if not valeurs:
        return STRATE_NON_ANNOTE
    return Counter(valeurs).most_common(1)[0][0]


def split_par_texte_unique(
    df: pd.DataFrame,
    cfg: Dict[str, Any],
    colonne_texte: str = "__text_raw__",
    colonne_strate: Optional[str] = None,
) -> pd.DataFrame:
    """Ajoute une colonne ``split`` au DataFrame, sans aucune fuite de texte.

    Les proportions de ``config.yaml → dataset`` sont visées **au niveau des
    lignes** (et non des groupes) : un texte répété 40 fois ne doit pas peser
    autant qu'un texte unique dans le respect du 70/15/15.

    Lève :class:`FuiteDetectee` si le résultat contient la moindre fuite — le
    contrôle fait partie de la fonction, pas d'un appel séparé qu'on peut
    oublier.
    """
    conf = cfg["dataset"]
    strate_col = colonne_strate or conf.get("stratify_on", "theme1_niv1")
    cibles = {
        "train": float(conf["split_train"]),
        "val": float(conf["split_val"]),
        "test": float(conf["split_test"]),
    }
    total = sum(cibles.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Les proportions de split ne somment pas à 1 : {cibles} ({total}).")
    seed = int(cfg.get("model", {}).get("seed", 42))

    if colonne_texte not in df.columns:
        raise KeyError(f"Colonne de texte absente : {colonne_texte!r}")

    # --- 1. Regroupement par texte unique ---------------------------------
    groupes: Dict[str, List[int]] = defaultdict(list)
    for pos, texte in enumerate(df[colonne_texte].tolist()):
        groupes[cle_texte(texte)].append(pos)

    labels_par_ligne = (df[strate_col].tolist() if strate_col in df.columns
                        else [None] * len(df))

    # --- 2. Répartition, strate par strate --------------------------------
    par_strate: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for cle, positions in groupes.items():
        strate = _strate_du_groupe([labels_par_ligne[p] for p in positions])
        par_strate[strate].append((cle, len(positions)))

    assignation: Dict[str, str] = {}
    rng = random.Random(seed)
    for strate in sorted(par_strate):
        membres = sorted(par_strate[strate])          # tri = déterminisme
        rng.shuffle(membres)
        n_lignes = sum(n for _, n in membres)
        quotas = {s: cibles[s] * n_lignes for s in SPLITS}
        courant = {s: 0.0 for s in SPLITS}
        # Les groupes les plus lourds d'abord : place les gros blocs pendant
        # qu'il reste de la marge, sinon ils font exploser le dernier quota.
        for cle, taille in sorted(membres, key=lambda kv: -kv[1]):
            choisi = max(SPLITS, key=lambda s: (quotas[s] - courant[s]) / max(cibles[s], 1e-9))
            assignation[cle] = choisi
            courant[choisi] += taille

    out = df.copy()
    out["split"] = [assignation[cle_texte(t)] for t in out[colonne_texte].tolist()]

    # --- 3. Contrôle bloquant ---------------------------------------------
    verifier_absence_de_fuite(out, colonne_texte=colonne_texte)

    repartition = Counter(out["split"])
    logger.info(
        "Split par texte unique : %d lignes / %d textes uniques — train %d (%.1f %%), "
        "val %d (%.1f %%), test %d (%.1f %%)",
        len(out), len(groupes),
        repartition["train"], 100 * repartition["train"] / max(len(out), 1),
        repartition["val"], 100 * repartition["val"] / max(len(out), 1),
        repartition["test"], 100 * repartition["test"] / max(len(out), 1),
    )
    return out


def verifier_absence_de_fuite(df: pd.DataFrame,
                              colonne_texte: str = "__text_raw__",
                              colonne_split: str = "split") -> None:
    """Échoue si un texte apparaît dans plus d'un split.

    Contrôle **bloquant** de la chaîne de préparation (invariant du projet).
    Utilisable seul, sur n'importe quel jeu déjà splitté, y compris produit par
    une autre chaîne.
    """
    manquantes = [c for c in (colonne_texte, colonne_split) if c not in df.columns]
    if manquantes:
        raise KeyError(f"Colonnes absentes pour le contrôle de fuite : {manquantes}")

    splits_par_texte: Dict[str, set] = defaultdict(set)
    for texte, split in zip(df[colonne_texte].tolist(), df[colonne_split].tolist()):
        splits_par_texte[cle_texte(texte)].add(split)

    fuites = {cle: sorted(s) for cle, s in splits_par_texte.items() if len(s) > 1}
    if fuites:
        apercu = list(fuites.items())[:5]
        detail = " ; ".join(f"{cle[:60]!r} -> {splits}" for cle, splits in apercu)
        raise FuiteDetectee(
            f"FUITE ENTRE SPLITS : {len(fuites)} texte(s) présent(s) dans plusieurs "
            f"splits sur {len(splits_par_texte)} textes uniques. Exemples : {detail}. "
            "Toute métrique calculée sur ce découpage mesurerait de la mémorisation. "
            "Le split doit porter sur le texte unique, jamais sur la ligne."
        )


def rapport_split(df: pd.DataFrame,
                  colonne_texte: str = "__text_raw__",
                  colonne_strate: str = "theme1_niv1") -> Dict[str, Any]:
    """Décrit le découpage produit — à joindre au protocole d'évaluation."""
    total = len(df)
    textes = {cle_texte(t) for t in df[colonne_texte].tolist()}
    par_split = {}
    for s in SPLITS:
        sub = df[df["split"] == s]
        par_split[s] = {
            "lignes": int(len(sub)),
            "part": round(len(sub) / max(total, 1), 4),
            "textes_uniques": len({cle_texte(t) for t in sub[colonne_texte].tolist()}),
            "annotes": int(sub[colonne_strate].notna().sum())
            if colonne_strate in sub.columns else None,
        }
    doublons = total - len(textes)
    return {
        "lignes": total,
        "textes_uniques": len(textes),
        "doublons_de_texte": doublons,
        "taux_de_doublons": round(doublons / max(total, 1), 4),
        "par_split": par_split,
        "fuite_detectee": False,
    }


# --------------------------------------------------------------------------- #
#  Jeu de recette GELÉ (L2) — le découpage est calculé une fois, puis relu
# --------------------------------------------------------------------------- #
#: Identité stable d'un verbatim, indépendante du texte et donc de toute option
#: de nettoyage. C'est cette clé qui porte le découpage gelé.
CLES_IDENTITE = ("__source__", "__respondent_id__", "__field__")


class SplitGeleIncoherent(RuntimeError):
    """Le découpage gelé ne couvre pas le corpus fourni."""


def _identite(df: pd.DataFrame) -> pd.Series:
    manquantes = [c for c in CLES_IDENTITE if c not in df.columns]
    if manquantes:
        raise KeyError(f"Colonnes d'identité absentes : {manquantes}")
    return (df[CLES_IDENTITE[0]].astype(str) + "\x1f"
            + df[CLES_IDENTITE[1]].astype(str) + "\x1f"
            + df[CLES_IDENTITE[2]].astype(str))


def ecrire_split_gele(df: pd.DataFrame, chemin) -> None:
    """Fige le découpage sur l'identité des verbatims, pas sur leur texte.

    **Pourquoi geler.** Le découpage dépend du texte utilisé pour regrouper les
    doublons. Recalculé sur le texte *nettoyé*, il change dès qu'une option de
    nettoyage change — mesuré : découper sur ``__text_raw__`` puis sur
    ``text_clean`` produit deux jeux de test qui ne partagent que **23,6 %** de
    leurs lignes. Comparer un modèle mesuré sur l'un à un modèle mesuré sur
    l'autre n'aurait aucun sens, et rien ne l'aurait signalé.

    Le fichier produit est le **jeu de recette gelé** exigé par L2 : il se
    versionne, se relit et ne bouge plus.
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    sortie = df[list(CLES_IDENTITE)].copy()
    sortie["split"] = df["split"].values
    sortie.to_csv(chemin, index=False, encoding="utf-8")
    logger.info("Découpage gelé écrit : %s (%d lignes)", chemin, len(sortie))


def appliquer_split_gele(df: pd.DataFrame, chemin) -> pd.DataFrame:
    """Applique un découpage gelé. Échoue si un verbatim n'y figure pas.

    L'échec est volontaire : un corpus qui a changé depuis le gel doit être
    re-gelé explicitement, jamais découpé à moitié en silence.
    """
    chemin = Path(chemin)
    gele = pd.read_csv(chemin, encoding="utf-8", dtype=str)
    table = dict(zip(_identite(gele), gele["split"]))
    ids = _identite(df)
    inconnus = int((~ids.isin(table)).sum())
    if inconnus:
        raise SplitGeleIncoherent(
            f"{inconnus} verbatim(s) sur {len(df)} sont absents du découpage gelé "
            f"({chemin.name}). Le corpus a changé depuis le gel : re-geler "
            "explicitement, en assumant que les mesures antérieures ne seront "
            "plus comparables."
        )
    out = df.copy()
    out["split"] = [table[i] for i in ids]
    return out


def split_ou_geler(df: pd.DataFrame, cfg: Dict[str, Any], chemin,
                   colonne_texte: str = "text_clean") -> pd.DataFrame:
    """Relit le découpage gelé s'il existe, le calcule et le fige sinon."""
    chemin = Path(chemin)
    if chemin.is_file():
        out = appliquer_split_gele(df, chemin)
        verifier_absence_de_fuite(out, colonne_texte=colonne_texte)
        logger.info("Découpage gelé relu depuis %s", chemin.name)
        return out
    out = split_par_texte_unique(df, cfg, colonne_texte=colonne_texte)
    ecrire_split_gele(out, chemin)
    return out
