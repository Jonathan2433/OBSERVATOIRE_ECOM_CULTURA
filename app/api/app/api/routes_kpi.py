"""Endpoints KPI : tableau de bord du lot, volumétrie globale, métriques modèle.

Deux principes tiennent ce module :

* **Le second thème compte.** Un verbatim peut porter deux thèmes (couche de
  décision, ``max_themes`` = 2). Une répartition qui ne regarde que
  ``theme1_niv1`` sous-compte mécaniquement les thèmes qui sortent souvent en
  second. Chaque répartition est donc publiée sous deux angles explicites :
  ``*_principal`` (un verbatim, une voix) et ``*_mentions`` (thème 1 + thème 2).
  Les deux sont légitimes et ne répondent pas à la même question — combien de
  verbatims parlent d'abord de ce sujet, contre combien l'évoquent.

* **Une note absente n'est pas un zéro.** La satisfaction est comptée sur les
  seules lignes notées ; ``n_sans_note`` porte le reste. Sans cela, toute
  moyenne plongerait au rythme des non-réponses.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from common.models import Batch, ModelVersion, Result

logger = logging.getLogger("api.kpi")

router = APIRouter(prefix="/api", tags=["kpi"], dependencies=[Depends(get_current_user)])

#: Bornes de l'échelle commune de satisfaction (D-20). Une note hors bornes
#: signale une donnée d'entrée non conforme : elle est comptée à part plutôt
#: qu'assimilée de force à la borne la plus proche.
SATISFACTION_MIN, SATISFACTION_MAX = 1, 4
#: Frontière satisfait / insatisfait sur l'échelle 1-4. L'échelle n'a pas de
#: point milieu : 1-2 sont les deux modalités négatives, 3-4 les positives.
SATISFACTION_SEUIL_SATISFAIT = 3


def _distribution(db: Session, batch_id: Optional[int], column) -> dict:
    """Répartition {valeur: n} sur une colonne, du plus fréquent au moins fréquent."""
    q = (
        db.query(column, func.count(Result.id))
        .filter(column.isnot(None), column != "")
    )
    if batch_id is not None:
        q = q.filter(Result.batch_id == batch_id)
    rows = q.group_by(column).all()
    return {k: v for k, v in sorted(rows, key=lambda x: -x[1])}


def _distribution_mentions(db: Session, batch_id: Optional[int], col1, col2) -> dict:
    """Répartition par MENTION : un verbatim bi-thème compte pour ses deux thèmes.

    La somme des valeurs dépasse donc le nombre de verbatims — c'est voulu, et
    c'est ce qui rend visibles les thèmes qui sortent surtout en second.
    """
    fusion: dict = {}
    for col in (col1, col2):
        for libelle, n in _distribution(db, batch_id, col).items():
            fusion[libelle] = fusion.get(libelle, 0) + n
    return dict(sorted(fusion.items(), key=lambda kv: -kv[1]))


def _theme_sentiment(db: Session, batch_id: Optional[int] = None) -> dict:
    """Croisement thème niv.1 × sentiment, EN MENTIONS -> {niv1: {sentiment: n}}.

    Le sentiment est propre à chaque thème depuis la V4 (une passe de sentiment
    par thème retenu) : un verbatim bi-thème peut être positif sur la livraison
    et négatif sur le produit. Empiler les deux mentions est la seule lecture
    qui ne perd pas cette information.
    """
    out: dict = {}
    paires = (
        (Result.theme1_niv1, Result.theme1_sentiment),
        (Result.theme2_niv1, Result.theme2_sentiment),
    )
    for col_theme, col_sent in paires:
        q = db.query(col_theme, col_sent, func.count(Result.id)).filter(
            col_theme.isnot(None), col_theme != "", col_sent.isnot(None), col_sent != "",
        )
        if batch_id is not None:
            q = q.filter(Result.batch_id == batch_id)
        for niv1, sent, n in q.group_by(col_theme, col_sent).all():
            bucket = out.setdefault(niv1, {})
            bucket[sent] = bucket.get(sent, 0) + n
    return dict(sorted(out.items(), key=lambda kv: -sum(kv[1].values())))


def _signal_counts(db: Session, batch_id: int) -> dict:
    base = db.query(func.count(Result.id)).filter(Result.batch_id == batch_id)
    return {
        "rupture": base.filter(Result.signal_rupture == True).scalar() or 0,  # noqa: E712
        "churn": base.filter(Result.signal_churn == True).scalar() or 0,  # noqa: E712
        "insatisfaction": base.filter(Result.signal_insatisfaction == True).scalar() or 0,  # noqa: E712
    }


def _n_bi_themes(db: Session, batch_id: Optional[int] = None) -> int:
    q = db.query(func.count(Result.id)).filter(
        Result.theme2_niv1.isnot(None), Result.theme2_niv1 != "")
    if batch_id is not None:
        q = q.filter(Result.batch_id == batch_id)
    return q.scalar() or 0


# --------------------------------------------------------------------------- #
#  Satisfaction (D-20)
# --------------------------------------------------------------------------- #
def _satisfaction(db: Session, batch_id: Optional[int] = None) -> dict:
    """Indicateurs de satisfaction déclarée, sur l'échelle commune 1-4.

    Distinct du signal ``insatisfaction`` : celui-ci est une DÉDUCTION du modèle
    sur le texte (note basse ET sentiment négatif), tandis qu'ici on restitue ce
    que le client a lui-même coché. Les deux peuvent diverger, et c'est
    précisément l'écart qui intéresse le pilotage.

    ``n_sans_note`` n'est pas un détail de présentation : les lots traités avant
    la migration 0010 n'ont aucune note conservée, ils tombent intégralement
    dans ce compteur. Un taux de satisfaction calculé sur zéro note doit
    s'afficher « non renseigné », pas « 0 % ».
    """
    base = db.query(Result)
    if batch_id is not None:
        base = base.filter(Result.batch_id == batch_id)

    n_total = base.with_entities(func.count(Result.id)).scalar() or 0
    notees = base.filter(Result.satisfaction.isnot(None))

    distribution = {
        str(note): n
        for note, n in sorted(
            notees.with_entities(Result.satisfaction, func.count(Result.id))
            .group_by(Result.satisfaction).all()
        )
    }
    n_notes = sum(distribution.values())
    moyenne = notees.with_entities(func.avg(Result.satisfaction)).scalar()
    n_satisfaits = (
        notees.filter(Result.satisfaction >= SATISFACTION_SEUIL_SATISFAIT)
        .with_entities(func.count(Result.id)).scalar() or 0
    )
    n_insatisfaits = (
        notees.filter(Result.satisfaction < SATISFACTION_SEUIL_SATISFAIT)
        .with_entities(func.count(Result.id)).scalar() or 0
    )
    hors_echelle = (
        notees.filter(or_(Result.satisfaction < SATISFACTION_MIN,
                          Result.satisfaction > SATISFACTION_MAX))
        .with_entities(func.count(Result.id)).scalar() or 0
    )

    return {
        "n_notes": n_notes,
        "n_sans_note": max(0, n_total - n_notes),
        "distribution": distribution,
        "moyenne": round(float(moyenne), 2) if moyenne is not None else None,
        "n_satisfaits": n_satisfaits,
        "n_insatisfaits": n_insatisfaits,
        "taux_satisfaction": (n_satisfaits / n_notes) if n_notes else None,
        "hors_echelle": hors_echelle,
        "par_source": _satisfaction_par_source(db, batch_id),
        "echelle": {"min": SATISFACTION_MIN, "max": SATISFACTION_MAX,
                    "seuil_satisfait": SATISFACTION_SEUIL_SATISFAIT},
        "sources_hypothese": list(_sources_echelle_hypothetique()),
    }


def _satisfaction_resume(db: Session, batch_id: Optional[int] = None) -> dict:
    """Moyenne et taux de satisfaction seuls — version légère pour les séries.

    La volumétrie parcourt tous les lots : y appeler le bloc complet
    multiplierait les requêtes par le nombre de lots pour des chiffres que le
    tableau n'affiche pas.
    """
    q = db.query(
        func.count(Result.id),
        func.avg(Result.satisfaction),
        func.sum(case((Result.satisfaction >= SATISFACTION_SEUIL_SATISFAIT, 1), else_=0)),
    ).filter(Result.satisfaction.isnot(None))
    if batch_id is not None:
        q = q.filter(Result.batch_id == batch_id)
    n, moyenne, n_sat = q.one()
    n, n_sat = int(n or 0), int(n_sat or 0)
    return {
        "moyenne": round(float(moyenne), 2) if moyenne is not None else None,
        "taux_satisfaction": (n_sat / n) if n else None,
    }


def _satisfaction_par_source(db: Session, batch_id: Optional[int] = None) -> dict:
    """Moyenne et taux de satisfaction par source fine (MDTC-postrecep…).

    Le cahier des charges §6 demande la répartition par source ET par score ;
    c'est aussi la seule vue qui rende visible qu'une source pèse sur la moyenne
    globale par son volume plutôt que par son niveau.
    """
    q = db.query(
        Result.source,
        func.count(Result.id),
        func.avg(Result.satisfaction),
        func.sum(case((Result.satisfaction >= SATISFACTION_SEUIL_SATISFAIT, 1), else_=0)),
    ).filter(Result.satisfaction.isnot(None))
    if batch_id is not None:
        q = q.filter(Result.batch_id == batch_id)

    out = {}
    for source, n, moyenne, n_sat in q.group_by(Result.source).all():
        n = int(n or 0)
        n_sat = int(n_sat or 0)
        out[source or "(source inconnue)"] = {
            "n_notes": n,
            "moyenne": round(float(moyenne), 2) if moyenne is not None else None,
            "taux_satisfaction": (n_sat / n) if n else None,
        }
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["n_notes"]))


@lru_cache(maxsize=1)
def _sources_echelle_hypothetique() -> tuple:
    """Sources dont la conversion vers l'échelle 1-4 est une HYPOTHÈSE eXalt.

    Q-17 est sans réponse : ni la table des libellés MDTC ni le rabattement
    Mopinion 1-5 → 1-4 n'ont été validés par Cultura. Tant que c'est le cas,
    tout chiffre agrégé entre sources repose sur une hypothèse, et l'écran doit
    le dire — un taux de satisfaction est exactement le genre de chiffre qui
    part en comité de direction sans son avertissement.

    La configuration est lue DIRECTEMENT en YAML, sans passer par ``src`` :
    l'image de l'API est volontairement sans torch et n'embarque pas le paquet
    ML. Elle a en revanche besoin du montage ``CONFIG_PATH`` — sans lui,
    l'avertissement disparaîtrait de l'écran sans que rien ne le signale.

    Échec explicite dans les journaux, silencieux à l'écran : l'interface
    retrouve son comportement d'origine plutôt que d'inventer un périmètre,
    mais l'exploitant voit passer la cause.
    """
    chemin = Path(os.getenv("CONFIG_PATH", "config/config.yaml"))
    try:
        import yaml

        with chemin.open(encoding="utf-8") as fichier:
            cfg = yaml.safe_load(fichier) or {}
        echelles = (cfg.get("cultura_sources") or {}).get("echelles_satisfaction") or {}
        return tuple(sorted(nom for nom, spec in echelles.items() if (spec or {}).get("hypothese")))
    except Exception as exc:  # pragma: no cover - dépend du montage de la config
        logger.warning("Statut des échelles de satisfaction indéterminable "
                       "(%s : %s) — configuration attendue en %s.",
                       type(exc).__name__, exc, chemin)
        return ()


@router.get("/batches/{batch_id}/kpi")
def batch_kpi(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    n_bi = _n_bi_themes(db, batch_id)
    n_classes = (
        db.query(func.count(Result.id))
        .filter(Result.batch_id == batch_id,
                Result.theme1_niv1.isnot(None), Result.theme1_niv1 != "")
        .scalar() or 0
    )
    return {
        "batch_id": batch.id,
        "label": batch.label,
        "status": batch.status,
        "model_label": batch.model_label,
        "n_total": batch.n_total,
        "n_processed": batch.n_processed,
        "n_review": batch.n_review,
        "review_rate": (batch.n_review / batch.n_total) if batch.n_total else 0.0,
        "n_errors": batch.n_errors,
        "duration_s": batch.duration_s,
        # Thème principal (une ligne, une voix).
        "themes": _distribution(db, batch_id, Result.theme1_niv1),
        "subthemes": _distribution(db, batch_id, Result.theme1_niv2),
        # Second thème seul, puis toutes mentions confondues.
        "themes_secondaires": _distribution(db, batch_id, Result.theme2_niv1),
        "subthemes_secondaires": _distribution(db, batch_id, Result.theme2_niv2),
        "themes_mentions": _distribution_mentions(db, batch_id, Result.theme1_niv1, Result.theme2_niv1),
        "subthemes_mentions": _distribution_mentions(db, batch_id, Result.theme1_niv2, Result.theme2_niv2),
        "n_bi_themes": n_bi,
        "taux_bi_themes": (n_bi / n_classes) if n_classes else 0.0,
        "sentiments": _distribution(db, batch_id, Result.theme1_sentiment),
        "sentiments_secondaires": _distribution(db, batch_id, Result.theme2_sentiment),
        "sources": _distribution(db, batch_id, Result.source),
        "signals": _signal_counts(db, batch_id),
        "theme_sentiment": _theme_sentiment(db, batch_id),
        "satisfaction": _satisfaction(db, batch_id),
    }


@router.get("/kpi/volumetry")
def volumetry(db: Session = Depends(get_db)):
    """Séries par lot (volume, taux de revue, signaux, satisfaction) + thèmes globaux."""
    batches = db.query(Batch).filter(Batch.status == "done").order_by(Batch.created_at).all()
    series = []
    for b in batches:
        sat = _satisfaction_resume(db, b.id)
        series.append({
            "id": b.id,
            "label": b.label,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "n_total": b.n_total,
            "n_review": b.n_review,
            "review_rate": (b.n_review / b.n_total) if b.n_total else 0.0,
            "signals": _signal_counts(db, b.id),
            "n_bi_themes": _n_bi_themes(db, b.id),
            "satisfaction_moyenne": sat["moyenne"],
            "taux_satisfaction": sat["taux_satisfaction"],
        })

    return {
        "n_batches": len(batches),
        "total_verbatims": sum(b.n_total for b in batches),
        "series": series,
        "global_themes": _distribution(db, None, Result.theme1_niv1),
        "global_themes_mentions": _distribution_mentions(
            db, None, Result.theme1_niv1, Result.theme2_niv1),
        "global_themes_secondaires": _distribution(db, None, Result.theme2_niv1),
        "n_bi_themes": _n_bi_themes(db, None),
        "theme_sentiment": _theme_sentiment(db, None),
        "satisfaction": _satisfaction(db, None),
    }


@router.get("/kpi/model")
def model_kpi(db: Session = Depends(get_db)):
    """Métriques de la version de modèle active (None si stub)."""
    active = db.query(ModelVersion).filter_by(is_active=True).first()
    if active is None:
        return {"active": None}
    return {
        "active": {
            "label": active.label,
            "kind": active.kind,
            "available": active.available,
            "metrics": active.metrics,
        }
    }
