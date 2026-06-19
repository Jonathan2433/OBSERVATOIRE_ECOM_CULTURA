"""Configuration applicative modifiable à chaud (table app_config).

Distincte de ``core.config.Settings`` (variables d'environnement, immuables au
runtime). Ici : paramètres éditables par l'admin (rétention, seuil par défaut).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from common.models import AppConfig

DEFAULTS = {
    "retention_months": "13",       # purge RGPD des lots au-delà
    "default_seuil_revue": "0.50",  # seuil de revue par défaut (calibré sur le modèle réel)
}


def get_all(db: Session) -> dict:
    rows = {c.key: c.value for c in db.query(AppConfig).all()}
    return {k: rows.get(k, DEFAULTS[k]) for k in DEFAULTS}


def get_value(db: Session, key: str) -> str:
    c = db.get(AppConfig, key)
    return c.value if c else DEFAULTS.get(key, "")


def set_value(db: Session, key: str, value) -> None:
    c = db.get(AppConfig, key)
    if c:
        c.value = str(value)
    else:
        db.add(AppConfig(key=key, value=str(value)))
    db.commit()


def retention_months(db: Session) -> int:
    try:
        return int(float(get_value(db, "retention_months")))
    except (TypeError, ValueError):
        return 13


def default_seuil_revue(db: Session) -> float:
    try:
        return float(get_value(db, "default_seuil_revue"))
    except (TypeError, ValueError):
        return 0.50
