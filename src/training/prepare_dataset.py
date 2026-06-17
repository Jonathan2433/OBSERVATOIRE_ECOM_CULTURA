"""Préparation du dataset d'entraînement à partir de historique_labels_poc.xlsx.

Chaîne de préparation :
  1. Chargement de l'historique labellisé.
  2. Anonymisation PII -> nettoyage du texte (MÊME pipeline qu'à l'inférence, afin
     que les distributions train/inférence coïncident et qu'AUCUNE PII n'atteigne
     le modèle).
  3. Split stratifié 70/15/15 (stratification sur theme1_niv1, qui couvre 99,6 %
     des verbatims mono-thème).
  4. Calcul des pondérations de classes (gestion des classes rares) sur le TRAIN.
  5. Sauvegarde :
       - data/processed/dataset.csv          (texte nettoyé + labels + split)
       - data/processed/encoders.json        (ordre des classes + class weights)
       - data/processed/dataset_stats.json   (statistiques de distribution)

Les encodeurs (ordre des labels) dérivent de la taxonomie : c'est l'unique
source de vérité, garantissant la cohérence train <-> inférence.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from ..preprocessing import Anonymizer, TextCleaner, load_historique
from ..utils import Taxonomy, load_config, resolve_path, set_seed

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Fonctions de construction des cibles (numpy pur — testables sans torch)
# --------------------------------------------------------------------------- #
def build_niv1_matrix(df: pd.DataFrame, taxonomy: Taxonomy) -> np.ndarray:
    """Matrice multi-label niv.1 (N, 20), ordre des colonnes = taxonomie."""
    mat = np.zeros((len(df), taxonomy.n_niv1), dtype=np.float32)
    for i, (_, row) in enumerate(df.iterrows()):
        for col in ("theme1_niv1", "theme2_niv1"):
            val = row.get(col)
            if isinstance(val, str) and val in taxonomy.niv1_to_idx:
                mat[i, taxonomy.niv1_to_idx[val]] = 1.0
    return mat


def explode_niv2_examples(df: pd.DataFrame, taxonomy: Taxonomy) -> Tuple[List[str], List[int]]:
    """(textes, indices niv.2) — une ligne par (verbatim, sous-thème).

    Les verbatims bi-thèmes (rares) génèrent 2 exemples. L'explosion intervient
    APRÈS le split : aucun verbatim n'est partagé entre train/val/test.
    """
    texts: List[str] = []
    idx: List[int] = []
    for _, row in df.iterrows():
        for col in ("theme1_niv2", "theme2_niv2"):
            val = row.get(col)
            if isinstance(val, str) and val in taxonomy.niv2_to_idx:
                texts.append(row["text_clean"])
                idx.append(taxonomy.niv2_to_idx[val])
    return texts, idx


def sentiment_targets(df: pd.DataFrame, sentiment_labels: List[str]) -> np.ndarray:
    """Indices de sentiment (sur theme1_sentiment) pour le modèle 3 classes."""
    lab2idx = {l: i for i, l in enumerate(sentiment_labels)}
    return np.array([lab2idx[s] for s in df["theme1_sentiment"]], dtype=np.int64)


# --------------------------------------------------------------------------- #
#  Pondérations de classes
# --------------------------------------------------------------------------- #
def _niv1_pos_weight(matrix: np.ndarray) -> np.ndarray:
    """pos_weight par classe pour BCEWithLogitsLoss : n_neg / n_pos."""
    n = matrix.shape[0]
    pos = matrix.sum(axis=0)
    neg = n - pos
    return (neg / np.clip(pos, 1, None)).astype(np.float32)


def _balanced_class_weight(counts: np.ndarray) -> np.ndarray:
    """Pondération 'balanced' : total / (n_classes * count_c)."""
    counts = np.clip(counts, 1, None)
    total = counts.sum()
    n_classes = len(counts)
    return (total / (n_classes * counts)).astype(np.float32)


# --------------------------------------------------------------------------- #
#  Pipeline principal
# --------------------------------------------------------------------------- #
def prepare_dataset(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Exécute toute la préparation et sauvegarde les artefacts. Renvoie un résumé."""
    set_seed(cfg["model"]["seed"])
    taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))

    # --- 1. Chargement ----------------------------------------------------
    hist = load_historique(resolve_path(cfg, cfg["paths"]["historique"]), cfg)
    logger.info("Historique chargé : %d verbatims labellisés.", len(hist))

    # --- 2. Anonymisation + nettoyage (même pipeline qu'à l'inférence) -----
    anonymizer = Anonymizer(cfg)
    cleaner = TextCleaner(cfg)
    total_pii = Counter()
    cleaned: List[str] = []
    for raw in hist["__text_raw__"]:
        masked, counts = anonymizer.anonymize(raw)
        total_pii.update(counts)
        cleaned.append(cleaner.clean(masked))
    hist["text_clean"] = cleaned
    logger.info("PII masquées sur l'historique : %s", dict(total_pii))

    n_short = int(sum(cleaner.is_too_short(t) for t in cleaned))
    n_empty = int(sum(cleaner.is_empty(t) for t in cleaned))
    if n_short or n_empty:
        logger.warning(
            "%d verbatims sous le seuil min_tokens, %d vides (conservés pour "
            "l'entraînement car labellisés, mais signalés).", n_short, n_empty
        )
    # On écarte uniquement les verbatims vides (aucun signal exploitable).
    before = len(hist)
    hist = hist[hist["text_clean"].str.strip() != ""].reset_index(drop=True)
    if len(hist) < before:
        logger.warning("%d verbatims vides écartés.", before - len(hist))

    # --- 3. Smoke test : sous-échantillonnage éventuel ---------------------
    if cfg.get("smoke_test", {}).get("enabled"):
        size = min(cfg["smoke_test"]["sample_size"], len(hist))
        hist = hist.sample(n=size, random_state=cfg["model"]["seed"]).reset_index(drop=True)
        logger.warning("SMOKE TEST : dataset réduit à %d lignes.", len(hist))

    # --- 4. Split stratifié 70/15/15 --------------------------------------
    strat_col = cfg["dataset"]["stratify_on"]
    train_frac = cfg["dataset"]["split_train"]
    val_frac = cfg["dataset"]["split_val"]
    test_frac = cfg["dataset"]["split_test"]
    seed = cfg["model"]["seed"]

    idx = np.arange(len(hist))
    strat = hist[strat_col]
    rel_val = val_frac / (val_frac + test_frac)

    def _split(arr, train_size, stratify):
        # Stratification si possible ; repli aléatoire si une classe est trop
        # rare pour être stratifiée (utile en mode smoke test / petits jeux).
        try:
            return train_test_split(arr, train_size=train_size, random_state=seed, stratify=stratify)
        except ValueError as exc:
            logger.warning("Stratification impossible (%s) -> split aléatoire.", exc)
            return train_test_split(arr, train_size=train_size, random_state=seed)

    train_idx, temp_idx = _split(idx, train_frac, strat)
    # Répartition val/test au sein des 30 % restants.
    val_idx, test_idx = _split(temp_idx, rel_val, strat.iloc[temp_idx])
    split = np.array(["train"] * len(hist), dtype=object)
    split[val_idx] = "val"
    split[test_idx] = "test"
    hist["split"] = split
    logger.info(
        "Split : train=%d val=%d test=%d",
        (split == "train").sum(), (split == "val").sum(), (split == "test").sum()
    )

    # --- 5. Pondérations de classes (calculées sur le TRAIN) --------------
    train_df = hist[hist["split"] == "train"]
    niv1_train = build_niv1_matrix(train_df, taxonomy)
    niv1_pos_weight = _niv1_pos_weight(niv1_train)

    niv2_counts = np.zeros(taxonomy.n_niv2, dtype=np.int64)
    for _, row in train_df.iterrows():
        for col in ("theme1_niv2", "theme2_niv2"):
            v = row.get(col)
            if isinstance(v, str) and v in taxonomy.niv2_to_idx:
                niv2_counts[taxonomy.niv2_to_idx[v]] += 1
    niv2_class_weight = _balanced_class_weight(niv2_counts)

    sentiment_labels = cfg["sentiment"]["labels"]
    sent_counts = np.array(
        [int((train_df["theme1_sentiment"] == l).sum()) for l in sentiment_labels],
        dtype=np.int64,
    )
    sentiment_class_weight = _balanced_class_weight(sent_counts)

    # --- 6. Détection des classes rares (sur l'ensemble du dataset) -------
    full_niv2_counts = Counter()
    for _, row in hist.iterrows():
        for col in ("theme1_niv2", "theme2_niv2"):
            v = row.get(col)
            if isinstance(v, str):
                full_niv2_counts[v] += 1
    warn_thr = cfg["dataset"]["rare_class_threshold_warn"]
    weight_thr = cfg["dataset"]["rare_class_threshold_weight"]
    rare_warn = {k: v for k, v in full_niv2_counts.items() if v < warn_thr}
    rare_weight = {k: v for k, v in full_niv2_counts.items() if v < weight_thr}
    for label, count in sorted(rare_weight.items(), key=lambda x: x[1]):
        if count < warn_thr:
            logger.warning("Classe niv.2 TRÈS rare (<%d ex.) : %r = %d", warn_thr, label, count)
        else:
            logger.info("Classe niv.2 rare (<%d ex., pondérée) : %r = %d", weight_thr, label, count)

    # --- 7. Sauvegarde ----------------------------------------------------
    proc_dir = resolve_path(cfg, cfg["paths"]["data_processed"])
    proc_dir.mkdir(parents=True, exist_ok=True)

    keep_cols = [
        "verbatim_original", "text_clean", "__source__", "__satisfaction__", "split",
        "nb_themes", "theme1_niv1", "theme1_niv2", "theme1_sentiment",
        "theme2_niv1", "theme2_niv2", "theme2_sentiment",
        "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte",
    ]
    keep_cols = [c for c in keep_cols if c in hist.columns]
    dataset_path = proc_dir / "dataset.csv"
    hist[keep_cols].to_csv(dataset_path, index=False, encoding="utf-8")

    encoders = {
        "niv1_labels": taxonomy.niv1_labels,
        "niv2_labels": taxonomy.niv2_labels,
        "sentiment_labels": sentiment_labels,
        "niv1_pos_weight": niv1_pos_weight.tolist(),
        "niv2_class_weight": niv2_class_weight.tolist(),
        "sentiment_class_weight": sentiment_class_weight.tolist(),
        "niv2_train_counts": niv2_counts.tolist(),
        "sentiment_train_counts": sent_counts.tolist(),
    }
    with open(proc_dir / "encoders.json", "w", encoding="utf-8") as fh:
        json.dump(encoders, fh, ensure_ascii=False, indent=2)

    stats = {
        "n_total": int(len(hist)),
        "n_train": int((split == "train").sum()),
        "n_val": int((split == "val").sum()),
        "n_test": int((split == "test").sum()),
        "pii_masked": dict(total_pii),
        "n_short": n_short,
        "n_empty": n_empty,
        "niv1_distribution": hist["theme1_niv1"].value_counts().to_dict(),
        "sentiment_distribution": hist["theme1_sentiment"].value_counts().to_dict(),
        "signal_rates": {
            s: float(hist[s].mean())
            for s in ("signal_rupture_client", "signal_churn", "signal_insatisfaction_forte")
            if s in hist.columns
        },
        "nb_themes_distribution": hist["nb_themes"].value_counts().to_dict() if "nb_themes" in hist else {},
        "rare_niv2_warn": rare_warn,
        "rare_niv2_weighted": rare_weight,
    }
    with open(proc_dir / "dataset_stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)

    logger.info("Artefacts sauvegardés dans %s", proc_dir)
    return stats


# --------------------------------------------------------------------------- #
#  Couche d'accès aux artefacts (contrat prepare -> train)
# --------------------------------------------------------------------------- #
class ProcessedDataset:
    """Accès lecture aux artefacts produits par :func:`prepare_dataset`."""

    def __init__(self, df: pd.DataFrame, encoders: Dict[str, Any], taxonomy: Taxonomy):
        self.df = df
        self.encoders = encoders
        self.taxonomy = taxonomy
        self.niv1_labels: List[str] = encoders["niv1_labels"]
        self.niv2_labels: List[str] = encoders["niv2_labels"]
        self.sentiment_labels: List[str] = encoders["sentiment_labels"]
        self.niv1_pos_weight = np.array(encoders["niv1_pos_weight"], dtype=np.float32)
        self.niv2_class_weight = np.array(encoders["niv2_class_weight"], dtype=np.float32)
        self.sentiment_class_weight = np.array(encoders["sentiment_class_weight"], dtype=np.float32)

    @classmethod
    def load(cls, cfg: Dict[str, Any]) -> "ProcessedDataset":
        proc_dir = resolve_path(cfg, cfg["paths"]["data_processed"])
        df = pd.read_csv(proc_dir / "dataset.csv", encoding="utf-8")
        # text_clean peut contenir des NaN si lecture CSV : on sécurise.
        df["text_clean"] = df["text_clean"].fillna("").astype(str)
        with open(proc_dir / "encoders.json", "r", encoding="utf-8") as fh:
            encoders = json.load(fh)
        taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))
        return cls(df, encoders, taxonomy)

    def split(self, name: str) -> pd.DataFrame:
        return self.df[self.df["split"] == name].reset_index(drop=True)

    def niv1_matrix(self, df: pd.DataFrame) -> np.ndarray:
        return build_niv1_matrix(df, self.taxonomy)

    def niv2_examples(self, df: pd.DataFrame) -> Tuple[List[str], List[int]]:
        return explode_niv2_examples(df, self.taxonomy)

    def sentiment_targets(self, df: pd.DataFrame) -> np.ndarray:
        return sentiment_targets(df, self.sentiment_labels)

    def signal_targets(self, df: pd.DataFrame, signal: str) -> np.ndarray:
        return df[signal].astype(int).to_numpy()


# --------------------------------------------------------------------------- #
#  Exécution directe
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    prepare_dataset(load_config())
