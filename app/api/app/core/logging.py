"""Configuration du logging structuré de l'API."""
from __future__ import annotations

import logging
from logging.config import dictConfig


def setup_logging(level: str = "INFO") -> None:
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            }
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "standard"}
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        },
    })
    logging.getLogger(__name__).info("Logging initialisé (niveau=%s)", level)
