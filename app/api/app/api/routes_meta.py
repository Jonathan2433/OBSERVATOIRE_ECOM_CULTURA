"""Métadonnées applicatives non sensibles (pour la page d'aide & les info-bulles).

Accessible à tout utilisateur authentifié (contrairement à /api/config, réservé
admin) : seuil de revue par défaut, modèle actif, et périmètre de mesure des
signaux. Aucune donnée sensible.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core import runtime_config as rc
from ..core.db import get_db
from ..core.security import get_current_user
from common.models import ModelVersion

logger = logging.getLogger("api.meta")

router = APIRouter(prefix="/api", tags=["meta"], dependencies=[Depends(get_current_user)])


def _signaux_non_mesures(active) -> list:
    """Signaux du contrat de sortie sans détecteur entraîné, POUR LE MODÈLE ACTIF.

    Arbitrage PO du 11/09 : l'interface doit distinguer « mesuré, négatif » de
    « non mesuré ». `churn` (64 positifs au corpus) et `rupture` (32) sont trop
    rares pour un détecteur évaluable (D-41) et sortent constamment à False ;
    les afficher comme une absence de signal ferait croire à Cultura qu'aucun
    client n'est en rupture, alors que nous ne l'avons pas cherché.

    Le périmètre dépend du moteur : le V1 possède les trois détecteurs, le
    modèle Cultura 2026 n'en a qu'un. Il est donc résolu sur le modèle ACTIF,
    jamais sur la configuration de référence — les deux coexistent depuis que le
    nouveau moteur s'ajoute à la sélection au lieu de remplacer l'ancien.

    Aucun modèle n'est chargé : la détection regarde les fichiers présents. En
    cas d'échec, on renvoie une liste vide — l'interface retombe alors sur son
    comportement d'origine plutôt que d'afficher un périmètre inventé.
    """
    if active is None or getattr(active, "kind", None) != "real":
        return []                     # stub, LM Studio, Claude : autre logique
    try:
        from src.inference.predictor import signaux_sans_modele
        from src.utils import config_du_profil, load_config, profil_par_racine

        cfg = load_config()
        profil = profil_par_racine(cfg, getattr(active, "path", None))
        return signaux_sans_modele(config_du_profil(cfg, profil) if profil else cfg)
    except Exception as exc:  # pragma: no cover - dépend du volume de modèles
        logger.warning("Périmètre de mesure des signaux indéterminable (%s).", exc)
        return []


@router.get("/meta")
def app_meta(db: Session = Depends(get_db)):
    active = db.query(ModelVersion).filter_by(is_active=True, available=True).first()
    return {
        "default_seuil_revue": rc.default_seuil_revue(db),
        "active_model": ({"label": active.label, "kind": active.kind} if active else None),
        # Noms courts : "rupture", "churn", "insatisfaction".
        "signaux_non_mesures": _signaux_non_mesures(active),
    }
