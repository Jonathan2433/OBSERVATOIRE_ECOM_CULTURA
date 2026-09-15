"""Datasets PyTorch pour le fine-tuning CamemBERT.

Un unique dataset générique ``EncodedDataset`` couvre les trois tâches
transformer (niv.1 multi-label, niv.2 multi-classes, sentiment) ; seules
changent la forme et le dtype des labels :
  - multi-label (niv.1)   : vecteur float (n_classes,)  -> BCEWithLogitsLoss
  - multi-classes (niv.2) : entier scalaire             -> CrossEntropyLoss
  - sentiment             : entier scalaire             -> CrossEntropyLoss

Les détecteurs de signaux n'utilisent PAS de Dataset torch : ils s'appuient sur
des embeddings CamemBERT gelés + une régression logistique scikit-learn
(cf. modeling.EmbeddingExtractor et training.train_signals).

La tokenisation est faite à la volée dans ``__getitem__`` (padding fixe à
``max_length``) : simple, robuste, et suffisant pour un POC CPU.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
import torch
from torch.utils.data import Dataset


class EncodedDataset(Dataset):
    """Tokenise des textes et fournit (input_ids, attention_mask, labels)."""

    def __init__(
        self,
        texts: Sequence[str],
        labels: Optional[np.ndarray],
        tokenizer,
        max_length: int,
        multilabel: bool = False,
        dynamic_padding: bool = True,
    ):
        self.texts = list(texts)
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.multilabel = multilabel
        self.dynamic_padding = bool(dynamic_padding)
        if labels is None:
            self.labels = None
        else:
            labels = np.asarray(labels)
            self.labels = labels.astype(np.float32) if multilabel else labels.astype(np.int64)
        if self.labels is not None and len(self.labels) != len(self.texts):
            raise ValueError("Nombre de labels != nombre de textes.")

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int):
        # `padding=False` : chaque exemple est tokenisé à sa longueur réelle, et
        # le lot est complété à la volée par :func:`collate_dynamique`.
        # Mesuré sur le corpus Cultura (médiane 10 tokens, moyenne 16,7 pour un
        # `max_length` de 256) : compléter à 256 coûte **7,3 fois** plus cher par
        # pas d'entraînement, soit 4,0 h contre 0,5 h pour une passe complète des
        # trois modèles. L'inférence, elle, utilisait déjà le padding dynamique.
        # Le résultat est numériquement équivalent : le masque d'attention neutralise
        # les positions complétées.
        enc = self.tokenizer(
            self.texts[idx],
            truncation=True,
            max_length=self.max_length,
            padding="max_length" if not self.dynamic_padding else False,
            return_tensors="pt" if not self.dynamic_padding else None,
        )
        if self.dynamic_padding:
            item = {
                "input_ids": enc["input_ids"],
                "attention_mask": enc["attention_mask"],
            }
        else:
            item = {
                "input_ids": enc["input_ids"].squeeze(0),
                "attention_mask": enc["attention_mask"].squeeze(0),
            }
        if self.labels is not None:
            item["labels"] = (self.labels[idx].tolist() if self.multilabel
                              else int(self.labels[idx]))
            if not self.dynamic_padding:
                item["labels"] = (torch.tensor(self.labels[idx], dtype=torch.float32)
                                  if self.multilabel
                                  else torch.tensor(self.labels[idx], dtype=torch.long))
        return item


# Alias sémantiques (cf. cahier des charges) — même implémentation, intentions
# distinctes côté code appelant.
class ClassificationDataset(EncodedDataset):
    """Dataset de classification thématique (niv.1 multi-label ou niv.2)."""


class SentimentDataset(EncodedDataset):
    """Dataset de classification de sentiment (3 classes)."""


def collate_dynamique(batch, tokenizer, multilabel: bool):
    """Complète un lot à la longueur de son plus long exemple, pas à `max_length`.

    Équivalent numérique du padding fixe — le masque d'attention neutralise les
    positions ajoutées — mais 7,3 fois moins coûteux sur ce corpus.
    """
    encodings = [{"input_ids": b["input_ids"], "attention_mask": b["attention_mask"]}
                 for b in batch]
    lot = tokenizer.pad(encodings, padding=True, return_tensors="pt")
    if "labels" in batch[0]:
        valeurs = [b["labels"] for b in batch]
        lot["labels"] = (torch.tensor(valeurs, dtype=torch.float32) if multilabel
                         else torch.tensor(valeurs, dtype=torch.long))
    return lot


def make_collate(tokenizer, multilabel: bool):
    """Fabrique le ``collate_fn`` à passer au ``DataLoader``."""
    def _collate(batch):
        return collate_dynamique(batch, tokenizer, multilabel)
    return _collate


def texts_to_loader(texts: List[str], tokenizer, max_length: int, batch_size: int):
    """DataLoader d'inférence (sans labels) — utilitaire pour l'extraction batch."""
    from torch.utils.data import DataLoader

    ds = EncodedDataset(texts, None, tokenizer, max_length, multilabel=False)
    return DataLoader(ds, batch_size=batch_size, shuffle=False,
                      collate_fn=make_collate(tokenizer, False))
