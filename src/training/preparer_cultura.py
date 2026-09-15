"""Chaîne de préparation du corpus Cultura 2026 — porte d'entrée du lot L6.

Enchaîne : chargeur (L1a) → anonymisation → nettoyage → split par texte unique
(L2, contrôle de fuite bloquant) → encodeurs dérivés du référentiel → poids de
classes calculés **sur le train seul** → artefacts versionnés.

Écrit dans un répertoire dédié (``data/processed/cultura_2026/``) et **ne touche
pas** aux artefacts de la V1 que l'application lit encore.

Choix d'exclusion à l'entraînement, tous issus de SPEC_CHARGEUR :

======================== ============================================================
``COUPLE_INVALIDE``      exclu — §8.4 : appariement faux, écarté et journalisé
``ANNOTATION_RECOPIEE``  exclu — §5.2 règle 3 : annotation recopiée d'un autre champ
``SENTIMENT_ABSENT``     exclu du **sentiment** seulement ; conservé pour les thèmes
``SOUSTHEME_HORS_...``   exclu du **niveau 2** seulement ; conservé pour le niveau 1
======================== ============================================================

Signaux : seul ``insatisfaction`` est entraîné (D-41). Churn (64 exemples) et
Rupture (32) sont trop rares pour produire un intervalle de confiance
exploitable ; ils restent au contrat de sortie, produits par règle.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..preprocessing import Anonymizer, TextCleaner
from ..preprocessing.anonymizer import verifier_ner_disponible
from ..preprocessing.cultura_loader import charger_cultura
from ..preprocessing.label_norm import (
    ANNOTATION_RECOPIEE,
    COUPLE_INVALIDE,
    SOUSTHEME_HORS_PERIMETRE,
    fold,
)
from ..utils.config import resolve_path
from ..utils.taxonomy import Taxonomy
from .split_sans_fuite import (
    rapport_split,
    split_ou_geler,
    verifier_absence_de_fuite,
)

logger = logging.getLogger(__name__)

SIGNAL_ENTRAINE = "insatisfaction"


# --------------------------------------------------------------------------- #
def _poids_multilabel(y: np.ndarray, plafond: Optional[float] = None) -> List[float]:
    """``pos_weight`` par classe pour ``BCEWithLogitsLoss`` : n_neg / n_pos.

    Le corpus Cultura est très déséquilibré au niveau 1 — `Réception commande`
    pèse 41 % des annotations, `Académie` moins de 1 % — ce qui porte le
    ``pos_weight`` jusqu'à **320**. À cette valeur, la perte pousse le modèle à
    répondre « oui » presque partout : mesuré à la première époque, précision
    0,144 pour un rappel de 0,954.

    Le remède prévu est le recalibrage du seuil multi-label (L5'), qui restaure
    la précision au moment de la décision. ``plafond`` offre un second levier si
    la courbe de seuil ne suffit pas : il borne le poids sans changer l'ordre des
    classes. ``None`` (défaut) conserve la formule d'origine.
    """
    n = y.shape[0]
    poids = []
    for j in range(y.shape[1]):
        pos = int(y[:, j].sum())
        neg = n - pos
        w = float(neg / pos) if pos > 0 else 1.0
        poids.append(min(w, float(plafond)) if plafond else w)
    return poids


def _poids_equilibres(labels: List[int], n_classes: int) -> List[float]:
    """``class_weight`` équilibré : total / (n_classes × effectif)."""
    compte = Counter(labels)
    total = len(labels)
    return [
        float(total / (n_classes * compte[c])) if compte.get(c) else 1.0
        for c in range(n_classes)
    ]


def _sans(anomalies: Any, code: str) -> bool:
    return code not in (anomalies or [])


# --------------------------------------------------------------------------- #
def preparer(cfg: Dict[str, Any],
             sortie: Optional[Path] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Produit le jeu prêt à l'entraînement et son rapport."""
    verifier_ner_disponible(cfg)

    taxo_path = resolve_path(cfg, cfg["cultura_sources"]["taxonomy"])
    taxonomy = Taxonomy.from_json(taxo_path)

    df, rapport_chargement = charger_cultura(cfg, taxonomy=taxonomy)

    # --- Anonymisation puis nettoyage, dans cet ordre (ENF-5) ----------------
    anonymizer = Anonymizer(cfg)
    cleaner = TextCleaner(cfg)
    pii: Counter = Counter()
    masques: List[str] = []
    for brut in df["__text_raw__"].tolist():
        masque, compte = anonymizer.anonymize(brut)
        pii.update(compte)
        masques.append(masque)
    df["text_clean"] = [cleaner.clean(m) for m in masques]

    # Un verbatim vide après nettoyage n'apprend rien.
    avant = len(df)
    garde = df["text_clean"].str.strip() != ""
    masques = [m for m, ok in zip(masques, garde.tolist()) if ok]
    df = df[garde].reset_index(drop=True)
    vides = avant - len(df)

    # --- Découpage : gelé une fois, relu ensuite -----------------------------
    # Le regroupement des doublons se fait sur un texte **canonique** (nettoyage
    # complet, minuscules forcées), et non sur `text_clean` : sans cela, changer
    # une option de nettoyage changerait le découpage. Mesuré : découper sur le
    # texte brut puis sur le texte nettoyé donne deux jeux de test qui ne
    # partagent que 23,6 % de leurs lignes.
    import copy

    cfg_canon = copy.deepcopy(cfg)
    cfg_canon.setdefault("cleaning", {})["lowercase"] = True
    cleaner_canon = TextCleaner(cfg_canon)
    df["_texte_groupe"] = [cleaner_canon.clean(m) for m in masques[:len(df)]] \
        if len(masques) == len(df) else [cleaner_canon.clean(t) for t in df["text_clean"]]

    chemin_gel = resolve_path(cfg, cfg["dataset"]["split_gele"])
    df = split_ou_geler(df, cfg, chemin_gel, colonne_texte="_texte_groupe")
    # Contrôle sur le texte réellement utilisé : un nettoyage moins agressif ne
    # peut que scinder des groupes, jamais en fusionner à cheval sur deux splits.
    verifier_absence_de_fuite(df, colonne_texte="text_clean")
    df = df.drop(columns=["_texte_groupe"])

    # --- Cibles ---------------------------------------------------------------
    hors_perimetre = {fold(s) for s in
                      cfg["label_normalization"]["sous_themes_hors_perimetre"]}

    exploitable = df["__anomalies__"].apply(
        lambda a: _sans(a, COUPLE_INVALIDE) and _sans(a, ANNOTATION_RECOPIEE))

    # Niveau 1 — multi-label sur les 11 thèmes (thème 1 + thème 2).
    y1 = np.zeros((len(df), taxonomy.n_niv1), dtype=int)
    for i, (t1, t2) in enumerate(zip(df["theme1_niv1"], df["theme2_niv1"])):
        for t in (t1, t2):
            if t and t in taxonomy.niv1_to_idx:
                y1[i, taxonomy.niv1_to_idx[t]] = 1
    a_niv1 = exploitable & (y1.sum(axis=1) > 0)

    # Niveau 2 — multi-classes sur le thème 1, hors sous-thèmes hors périmètre.
    niv2_idx: List[Optional[int]] = []
    for s1, anomalies in zip(df["theme1_niv2"], df["__anomalies__"]):
        if (s1 and s1 in taxonomy.niv2_to_idx
                and fold(s1) not in hors_perimetre
                and SOUSTHEME_HORS_PERIMETRE not in (anomalies or [])):
            niv2_idx.append(taxonomy.niv2_to_idx[s1])
        else:
            niv2_idx.append(None)
    df["y_niv2"] = niv2_idx
    a_niv2 = exploitable & df["y_niv2"].notna()

    # Sentiment — 3 classes.
    labels_sent = cfg["sentiment"]["labels"]
    idx_sent = {lab: i for i, lab in enumerate(labels_sent)}
    df["y_sentiment"] = [idx_sent.get(s) if s else None for s in df["sentiment"]]
    a_sent = exploitable & df["y_sentiment"].notna()

    # Signal — D-41 : seul `insatisfaction` est entraîné.
    df["y_signal"] = [1 if s == SIGNAL_ENTRAINE else 0 for s in df["signal"]]
    a_signal = exploitable.copy()

    for nom, masque in (("niv1", a_niv1), ("niv2", a_niv2),
                        ("sentiment", a_sent), ("signal", a_signal)):
        df[f"apprend_{nom}"] = masque.values

    # --- Poids, calculés sur le TRAIN uniquement ------------------------------
    est_train = df["split"] == "train"
    tr1 = est_train & df["apprend_niv1"]
    tr2 = est_train & df["apprend_niv2"]
    trs = est_train & df["apprend_sentiment"]

    encodeurs = {
        "source": str(taxo_path.name),
        "niv1_labels": taxonomy.niv1_labels,
        "niv2_labels": taxonomy.niv2_labels,
        "sentiment_labels": labels_sent,
        "signal_entraine": SIGNAL_ENTRAINE,
        "niv2_hors_perimetre": sorted(
            cfg["label_normalization"]["sous_themes_hors_perimetre"]),
        "poids_niv1_pos_weight": _poids_multilabel(
            y1[tr1.values], cfg["dataset"].get("pos_weight_max")),
        "pos_weight_max": cfg["dataset"].get("pos_weight_max"),
        "poids_niv2": _poids_equilibres(
            [int(v) for v in df.loc[tr2, "y_niv2"].tolist()], taxonomy.n_niv2),
        "poids_sentiment": _poids_equilibres(
            [int(v) for v in df.loc[trs, "y_sentiment"].tolist()], len(labels_sent)),
        "politique_prefixe": __import__(
            "src.utils.features", fromlist=["politique_prefixe"]
        ).politique_prefixe(cfg),
        "cleaning": dict(cfg.get("cleaning", {})),
    }

    # --- Classes rares --------------------------------------------------------
    seuil_avert = cfg["dataset"]["rare_class_threshold_warn"]
    compte2 = Counter(int(v) for v in df.loc[tr2, "y_niv2"].tolist())
    rares = {taxonomy.niv2_labels[i]: compte2.get(i, 0)
             for i in range(taxonomy.n_niv2)
             if taxonomy.niv2_labels[i] not in encodeurs["niv2_hors_perimetre"]
             and compte2.get(i, 0) < seuil_avert}

    rapport = {
        "corpus": rapport_chargement["verbatims_produits"],
        "verbatims_vides_apres_nettoyage": int(vides),
        "retenus": int(len(df)),
        "pii_masquees": dict(pii),
        "split": rapport_split(df, colonne_texte="text_clean"),
        "split_gele": str(chemin_gel),
        "exemples_par_tache": {
            "niv1": {s: int(((df["split"] == s) & df["apprend_niv1"]).sum())
                     for s in ("train", "val", "test")},
            "niv2": {s: int(((df["split"] == s) & df["apprend_niv2"]).sum())
                     for s in ("train", "val", "test")},
            "sentiment": {s: int(((df["split"] == s) & df["apprend_sentiment"]).sum())
                          for s in ("train", "val", "test")},
            "signal_insatisfaction": {
                "positifs_train": int((est_train & (df["y_signal"] == 1)).sum()),
                "total_train": int(est_train.sum()),
            },
        },
        "exclusions": {
            "couple_invalide": int(df["__anomalies__"].apply(
                lambda a: COUPLE_INVALIDE in (a or [])).sum()),
            "annotation_recopiee": int(df["__anomalies__"].apply(
                lambda a: ANNOTATION_RECOPIEE in (a or [])).sum()),
            "soustheme_hors_perimetre": int(df["__anomalies__"].apply(
                lambda a: SOUSTHEME_HORS_PERIMETRE in (a or [])).sum()),
        },
        "classes_rares_niv2_train": dict(sorted(rares.items(), key=lambda kv: kv[1])),
        "n_niv2_entrainables": taxonomy.n_niv2 - len(encodeurs["niv2_hors_perimetre"]),
    }

    if sortie is not None:
        sortie = Path(sortie)
        sortie.mkdir(parents=True, exist_ok=True)
        colonnes = [
            "__source__", "__respondent_id__", "__field__", "text_clean",
            "__satisfaction__", "__date__", "split",
            "theme1_niv1", "theme1_niv2", "theme2_niv1", "theme2_niv2",
            "sentiment", "signal", "y_niv2", "y_sentiment", "y_signal",
            "apprend_niv1", "apprend_niv2", "apprend_sentiment", "apprend_signal",
        ]
        df[colonnes].to_csv(sortie / "dataset.csv", index=False, encoding="utf-8")
        np.save(sortie / "y_niv1.npy", y1)
        (sortie / "encoders.json").write_text(
            json.dumps(encodeurs, ensure_ascii=False, indent=2), encoding="utf-8")
        (sortie / "dataset_stats.json").write_text(
            json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    return df, rapport
