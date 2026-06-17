#!/usr/bin/env python
"""Pipeline d'entraînement complet (hors ligne après setup_models.py).

Enchaîne : prepare_dataset -> classifier (niv.1 + niv.2) -> sentiment ->
signals -> export ONNX int8 -> évaluation.

Durée indicative sur CPU standard : ~2-4 h sur les données complètes.
Pour une validation rapide de bout en bout (~quelques minutes) : option --smoke.

Usage :
    python scripts/run_training.py                # entraînement complet
    python scripts/run_training.py --smoke        # smoke test rapide
    python scripts/run_training.py --skip-onnx    # sans export ONNX
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.modeling import export_onnx_int8  # noqa: E402
from src.utils import load_config, resolve_path, set_seed  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("run_training")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Entraînement complet du pipeline Cultura.")
    p.add_argument("--config", default=None, help="Chemin d'un config.yaml alternatif.")
    p.add_argument("--smoke", action="store_true", help="Smoke test rapide (sous-échantillon).")
    p.add_argument("--skip-prepare", action="store_true", help="Ne pas refaire prepare_dataset.")
    p.add_argument("--skip-onnx", action="store_true", help="Ne pas exporter en ONNX/int8.")
    p.add_argument("--skip-eval", action="store_true", help="Ne pas lancer l'évaluation finale.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    if args.smoke:
        cfg["smoke_test"]["enabled"] = True
        logger.warning("MODE SMOKE TEST : entraînement réduit (NON destiné à la production).")
    set_seed(cfg["model"]["seed"])

    t0 = time.time()

    # --- 1. Préparation des données -------------------------------------------
    if not args.skip_prepare:
        from src.training.prepare_dataset import prepare_dataset
        logger.info(">>> Étape 1/5 : préparation du dataset")
        prepare_dataset(cfg)

    # --- 2. Classification thématique (niv.1 + niv.2) -------------------------
    from src.training.train_classifier import train_classifier
    logger.info(">>> Étape 2/5 : classification thématique (niv.1 + niv.2)")
    train_classifier(cfg)

    # --- 3. Sentiment ----------------------------------------------------------
    from src.training.train_sentiment import train_sentiment
    logger.info(">>> Étape 3/5 : modèle de sentiment")
    train_sentiment(cfg)

    # --- 4. Signaux ------------------------------------------------------------
    from src.training.train_signals import train_signals
    logger.info(">>> Étape 4/5 : détecteurs de signaux")
    train_signals(cfg)

    # --- 5a. Export ONNX int8 --------------------------------------------------
    if not args.skip_onnx and cfg.get("onnx", {}).get("enabled", True):
        logger.info(">>> Export ONNX int8 des modèles transformer")
        for key in ("model_classifier_niv1", "model_classifier_niv2", "model_sentiment"):
            try:
                export_onnx_int8(resolve_path(cfg, cfg["paths"][key]), cfg)
            except Exception as exc:  # pragma: no cover
                logger.warning("Export ONNX échoué pour %s (%s).", key, exc)

    # --- 5b. Évaluation --------------------------------------------------------
    if not args.skip_eval:
        from src.evaluation.evaluate import evaluate
        logger.info(">>> Étape 5/5 : évaluation sur le jeu de test")
        evaluate(cfg)

    dt = time.time() - t0
    logger.info("=== Entraînement complet terminé en %d min %d s ===", int(dt // 60), int(dt % 60))


if __name__ == "__main__":
    main()
