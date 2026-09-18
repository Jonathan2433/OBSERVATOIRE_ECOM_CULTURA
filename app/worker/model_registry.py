"""Registre des moteurs : découverte et synchronisation en base.

- Le **stub** (heuristique mots-clés) est toujours disponible.
- Le modèle **réel** est détecté si les artefacts CamemBERT sont présents dans
  le volume monté (/data/models). Ses métriques sont lues depuis eval_report.json.
- LM Studio est disponible si son service, son modèle et son référentiel répondent.
- Claude reste un moteur de comparaison conditionné à la présence de sa clé.

La synchronisation est exécutée par le worker (qui a accès au volume + au moteur
`src`). L'API ne fait que lire/activer les entrées en base.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.db import SessionLocal
from common.models import (
    MODEL_KIND_CLAUDE, MODEL_KIND_LMSTUDIO, MODEL_KIND_REAL, MODEL_KIND_STUB, ModelVersion,
)

logger = logging.getLogger("worker.registry")

STUB_LABEL = "stub-heuristique"


def _summary_metrics(report: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(report.get("niv1"), dict):
        out["f1_macro_niv1"] = report["niv1"].get("f1_macro")
    if isinstance(report.get("niv2"), dict):
        out["f1_macro_niv2"] = report["niv2"].get("f1_macro")
    if isinstance(report.get("sentiment"), dict):
        out["accuracy_sentiment"] = report["sentiment"].get("accuracy")
    sig = report.get("signals", {})
    if isinstance(sig, dict) and isinstance(sig.get("rupture"), dict):
        out["recall_rupture"] = sig["rupture"].get("recall")
    return out


def _detect_camembert(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Détecte TOUS les moteurs CamemBERT déclarés et réellement présents.

    Arbitrage PO du 11/09 : le modèle Cultura 2026 s'ajoute à la sélection, il
    ne remplace pas le V1. Les profils sont déclarés en configuration
    (`moteurs_camembert`) ; un profil dont les quatre sous-modèles ne sont pas
    tous présents est simplement ignoré — un modèle en cours de dépôt ne doit
    pas apparaître comme sélectionnable.
    """
    from src.utils import libelle_modele, modele_present, profils, resolve_path

    trouves: List[Dict[str, Any]] = []
    for profil in profils(cfg):
        if not modele_present(cfg, profil):
            logger.info("Profil de moteur « %s » : modèle absent ou incomplet -> ignoré.",
                        profil.get("id"))
            continue
        # Chaque profil publie SES métriques. Publier celles du V1 sous le
        # libellé du modèle 2026 (ou l'inverse) tromperait les tableaux de bord
        # sur exactement le point qu'ils servent à surveiller.
        #
        # Un profil peut soit désigner un rapport d'évaluation, soit déclarer
        # directement ses chiffres. La seconde forme sert quand le rapport
        # existant est INVALIDE : le moteur V1 n'a d'autre évaluation thématique
        # que celle du 18/06, mesurée sur un découpage fuité à 99,6 %. Publier
        # des chiffres faux est pire que n'en publier aucun — c'est précisément
        # ainsi que ce défaut a survécu deux mois.
        metrics = profil.get("metriques")
        rapport = profil.get("eval_report")
        if metrics is None and rapport:
            chemin = Path(resolve_path(cfg, rapport))
            if chemin.is_file():
                try:
                    with open(chemin, "r", encoding="utf-8") as fh:
                        metrics = _summary_metrics(json.load(fh))
                except Exception:  # pragma: no cover
                    metrics = None
            else:
                logger.info("Profil « %s » : rapport d'évaluation absent (%s).",
                            profil.get("id"), rapport)
        elif metrics is None:
            logger.info("Profil « %s » : aucune métrique publiable déclarée.",
                        profil.get("id"))
        trouves.append({
            "label": libelle_modele(cfg, profil),
            "path": str(resolve_path(cfg, profil["racine"])),
            "metrics": metrics,
            "profil": profil.get("id"),
            "libelle_profil": profil.get("libelle") or profil.get("id"),
        })
    return trouves


def _detect_lmstudio(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sonde le moteur LM Studio (V4). None si le moteur est désactivé en config.

    Si activé, renvoie toujours une entrée (pour que l'admin la voie) avec un drapeau
    ``available`` dynamique : vrai uniquement si LM Studio répond, si le modèle est
    chargé et si le référentiel configuré est lisible. Le « test de connexion » côté
    UI = relancer cette synchro (Re-scanner).
    """
    lms = cfg.get("lmstudio", {}) or {}
    if not lms.get("enabled"):
        return None

    model = lms.get("model", "local-model")
    base_url = lms.get("base_url", "http://host.docker.internal:1234/v1")
    label = f"lmstudio:{model}"
    taxonomy_path = None
    taxonomy_present = True
    if lms.get("taxonomy"):
        try:
            from src.utils import resolve_path

            taxonomy_path = str(resolve_path(cfg, lms["taxonomy"]))
            taxonomy_present = Path(taxonomy_path).is_file()
        except Exception as exc:
            taxonomy_present = False
            logger.warning("Référentiel LM Studio invalide (%s) : %s", lms.get("taxonomy"), exc)
    reachable, present = False, False
    try:
        from .lmstudio_predictor import list_llm_models, model_is_installed

        installed = list_llm_models(base_url, timeout_s=5)  # ping court (test de connexion)
        reachable = True
        present = model_is_installed(model, installed)
    except Exception as exc:  # LMStudioError ou import : injoignable
        logger.info("LM Studio non disponible (%s) : %s", base_url, exc)

    return {
        "label": label,
        "available": bool(reachable and present and taxonomy_present),
        "path": f"{model} @ {base_url}",
        "metrics": {
            "reachable": reachable,
            "model_present": present,
            "model": model,
            "taxonomy_path": taxonomy_path,
            "taxonomy_present": taxonomy_present,
            "prompt_version": lms.get("prompt_version"),
            "contract_version": lms.get("contract_version"),
        },
    }


def _detect_claude(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Décrit le moteur Claude (V5). None si désactivé en config.

    **Comparaison/test uniquement** : l'entrée n'est jamais auto-activée et son
    activation est refusée côté serveur. ``available`` = vrai ssi une clé
    ``ANTHROPIC_API_KEY`` est présente — détection **offline** (aucun ping réseau :
    on ne contacte Anthropic que lors d'un test/comparaison explicite). La présence
    de la clé est transmise par ``config_worker`` via ``api_key_present`` (le secret
    lui-même n'entre jamais dans la config).
    """
    cl = cfg.get("claude", {}) or {}
    if not cl.get("enabled"):
        return None

    model = cl.get("model", "claude-opus-4-8")
    base_url = cl.get("base_url", "https://api.anthropic.com")
    key_present = bool(cl.get("api_key_present"))
    return {
        "label": f"claude:{model}",
        "available": key_present,
        "path": f"{model} @ {base_url}",
        "metrics": {"api_key_present": key_present, "model": model, "comparison_only": True},
    }


def sync_registry(cfg: Dict[str, Any]) -> None:
    """Met à jour le registre : stub + modèle réel + LM Studio (si activé) + Claude (si activé)."""
    with SessionLocal() as db:
        stub = db.query(ModelVersion).filter_by(label=STUB_LABEL).one_or_none()
        if stub is None:
            stub = ModelVersion(kind=MODEL_KIND_STUB, label=STUB_LABEL, available=True)
            db.add(stub)
            db.flush()
        else:
            stub.available = True

        try:
            camemberts = _detect_camembert(cfg)
        except Exception as exc:  # pragma: no cover
            logger.warning("Détection des modèles CamemBERT impossible : %s", exc)
            camemberts = []

        detectes = {}
        for moteur in camemberts:
            existing = db.query(ModelVersion).filter_by(label=moteur["label"]).one_or_none()
            if existing is None:
                existing = ModelVersion(
                    kind=MODEL_KIND_REAL, label=moteur["label"], path=moteur["path"],
                    metrics=moteur["metrics"], available=True,
                )
                db.add(existing)
            else:
                existing.available = True
                existing.path = moteur["path"]
                existing.metrics = moteur["metrics"]
            detectes[moteur["label"]] = existing
            logger.info("Moteur CamemBERT détecté : %s (%s)",
                        moteur["label"], moteur["libelle_profil"])
        if not camemberts:
            logger.info("Aucun modèle CamemBERT détecté -> mode stub.")

        _neutraliser_entrees_perimees(db, detectes)

        # --- Moteur LM Studio (V4) : enregistré uniquement si activé en config --
        lmstudio = _detect_lmstudio(cfg)
        if lmstudio:
            existing = db.query(ModelVersion).filter_by(label=lmstudio["label"]).one_or_none()
            if existing is None:
                db.add(ModelVersion(
                    kind=MODEL_KIND_LMSTUDIO, label=lmstudio["label"], path=lmstudio["path"],
                    metrics=lmstudio["metrics"], available=lmstudio["available"],
                ))
            else:
                existing.available = lmstudio["available"]
                existing.path = lmstudio["path"]
                existing.metrics = lmstudio["metrics"]
            logger.info("Moteur LM Studio %s : disponible=%s", lmstudio["label"], lmstudio["available"])
        else:
            # Moteur désactivé : neutraliser toute entrée LM Studio résiduelle.
            for row in db.query(ModelVersion).filter_by(kind=MODEL_KIND_LMSTUDIO).all():
                row.available = False

        # --- Moteur Claude (V5) : comparaison/test uniquement, JAMAIS auto-activé --
        claude = _detect_claude(cfg)
        if claude:
            existing = db.query(ModelVersion).filter_by(label=claude["label"]).one_or_none()
            if existing is None:
                db.add(ModelVersion(
                    kind=MODEL_KIND_CLAUDE, label=claude["label"], path=claude["path"],
                    metrics=claude["metrics"], available=claude["available"],
                ))
            else:
                existing.available = claude["available"]
                existing.path = claude["path"]
                existing.metrics = claude["metrics"]
            logger.info("Moteur Claude %s : disponible=%s (comparaison uniquement)",
                        claude["label"], claude["available"])
        else:
            # Moteur désactivé : neutraliser toute entrée Claude résiduelle.
            for row in db.query(ModelVersion).filter_by(kind=MODEL_KIND_CLAUDE).all():
                row.available = False

        # Garantir au moins un modèle actif (jamais Claude : non activable).
        if db.query(ModelVersion).filter_by(is_active=True).count() == 0:
            stub.is_active = True
        db.commit()


def _neutraliser_entrees_perimees(db, detectes: Dict[str, Any]) -> None:
    """Retire du sélecteur les entrées CamemBERT qui ne correspondent plus à rien.

    Deux cas, à ne pas confondre :

    * **Même modèle, libellé différent.** Le libellé du registre a changé quand
      les profils sont apparus (`camembert-<horodatage>` ->
      `camembert-<profil>-<horodatage>`). L'ancienne entrée désigne le MÊME
      répertoire : elle est neutralisée, et si elle était active, la nouvelle
      **reprend l'activation**. Renommer une ligne de registre ne doit pas
      changer le modèle que l'application sert.
    * **Modèle réellement disparu.** Artefacts retirés du volume : l'entrée est
      simplement rendue indisponible. Si elle était active, `get_active` retombe
      sur le stub — visible, plutôt qu'une inférence avec des poids absents.
    """
    perimees = [m for m in db.query(ModelVersion).filter_by(kind=MODEL_KIND_REAL).all()
                if m.label not in detectes]
    par_chemin = {m.path: m for m in detectes.values() if m.path}
    for ancienne in perimees:
        remplacante = par_chemin.get(ancienne.path)
        if remplacante is not None and ancienne.is_active:
            remplacante.is_active = True
            logger.info(
                "Entrée « %s » renommée en « %s » (même modèle, %s) : "
                "l'activation est reportée sur la nouvelle.",
                ancienne.label, remplacante.label, ancienne.path)
        elif ancienne.is_active:
            logger.warning(
                "Modèle actif « %s » introuvable sur le volume (%s) : rendu "
                "indisponible. L'application retombe sur le stub tant qu'un "
                "moteur n'est pas sélectionné.", ancienne.label, ancienne.path)
        ancienne.is_active = False
        ancienne.available = False


def get_active(db) -> Optional[ModelVersion]:
    """Modèle actif (repli sur le stub si l'actif est indisponible)."""
    active = db.query(ModelVersion).filter_by(is_active=True, available=True).first()
    if active:
        return active
    return db.query(ModelVersion).filter_by(label=STUB_LABEL).first()
