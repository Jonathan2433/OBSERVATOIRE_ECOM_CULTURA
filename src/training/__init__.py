"""Entraînement : préparation des données, datasets PyTorch, fine-tuning.

Note : ``prepare_dataset`` ne dépend pas de torch (utilisable en environnement
allégé). Les fonctions de fine-tuning (train_classifier/sentiment/signals) sont
importées paresseusement via leurs modules pour éviter d'imposer torch ici.
"""

from .prepare_dataset import prepare_dataset, ProcessedDataset

__all__ = ["prepare_dataset", "ProcessedDataset"]
