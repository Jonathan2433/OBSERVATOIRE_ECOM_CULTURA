"""Briques de modélisation partagées entre l'entraînement et l'inférence.

Ce module est le CONTRAT commun garantissant que l'inférence reconstruit
exactement la même architecture/tokenisation que l'entraînement.
"""

from .architecture import (
    load_tokenizer,
    build_sequence_classifier,
    save_versioned,
    resolve_model_dir,
    TorchSeqClassifier,
    OnnxSeqClassifier,
    EmbeddingExtractor,
    load_classifier,
    export_onnx_int8,
    base_model_path,
)

__all__ = [
    "load_tokenizer",
    "build_sequence_classifier",
    "save_versioned",
    "resolve_model_dir",
    "TorchSeqClassifier",
    "OnnxSeqClassifier",
    "EmbeddingExtractor",
    "load_classifier",
    "export_onnx_int8",
    "base_model_path",
]
