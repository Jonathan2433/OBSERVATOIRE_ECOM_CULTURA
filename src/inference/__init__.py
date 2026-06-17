"""Inférence : prédiction par verbatim, traitement par lots, file de revue."""

from .predictor import VerbatimPredictor, build_output, OUTPUT_COLUMNS

__all__ = ["VerbatimPredictor", "build_output", "OUTPUT_COLUMNS"]
