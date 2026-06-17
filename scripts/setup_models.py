#!/usr/bin/env python
"""Téléchargement initial des modèles (À EXÉCUTER UNE FOIS, avec internet).

Télécharge et stocke EN LOCAL :
  - CamemBERT (tokenizer + encodeur de base) dans data/models/camembert-base/ ;
  - le modèle spaCy français fr_core_news_sm (anonymisation NER).

Après cette étape, tout le pipeline (entraînement + inférence) fonctionne HORS
LIGNE : aucun appel réseau n'est effectué (local_files_only côté transformers).

Usage :
    python scripts/setup_models.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Permet `import src...` quel que soit le cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils import load_config, resolve_path  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("setup_models")


def download_camembert(cfg) -> None:
    from transformers import AutoModel, AutoTokenizer

    base = cfg["model"]["base_model"]
    local_dir = resolve_path(cfg, cfg["model"]["local_model_dir"])
    local_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Téléchargement de '%s' -> %s", base, local_dir)

    tokenizer = AutoTokenizer.from_pretrained(base)
    model = AutoModel.from_pretrained(base)  # encodeur de base (têtes ajoutées au fine-tuning)
    tokenizer.save_pretrained(local_dir)
    model.save_pretrained(local_dir)
    logger.info("CamemBERT stocké en local. Mode hors ligne désormais possible.")


def download_spacy(cfg) -> None:
    model_name = cfg["anonymization"]["spacy_model"]
    try:
        import spacy

        try:
            spacy.load(model_name)
            logger.info("Modèle spaCy '%s' déjà présent.", model_name)
            return
        except OSError:
            pass
        logger.info("Téléchargement du modèle spaCy '%s'...", model_name)
        from spacy.cli import download as spacy_download

        spacy_download(model_name)
        spacy.load(model_name)
        logger.info("Modèle spaCy '%s' installé.", model_name)
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "Échec d'installation de spaCy '%s' (%s). Lancez manuellement : "
            "python -m spacy download %s", model_name, exc, model_name
        )


def main() -> None:
    cfg = load_config()
    logger.info("=== Configuration initiale des modèles (internet requis) ===")
    download_camembert(cfg)
    download_spacy(cfg)
    logger.info("=== Terminé. Vous pouvez maintenant lancer run_training.py hors ligne. ===")


if __name__ == "__main__":
    main()
