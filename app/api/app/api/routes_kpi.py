"""Endpoints KPI : thèmes à la maille verbatim, satisfaction à la maille répondant."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from common.models import Batch, ModelVersion, Result, SurveyResponse

router = APIRouter(prefix="/api", tags=["kpi"], dependencies=[Depends(get_current_user)])

SATISFACTION_MIN = 1
CLIENT_STATUSES = ("ancien", "nouveau", "non_renseigne")
CLASSIFICATION_TOP_N = 5
EXPECTED_SOURCE_SCALES = {
    "MDTC-postachat": 4,
    "MDTC-postrecep": 4,
    "Mopinion-desktop": 5,
    "Mopinion-mobile": 5,
}
EXPECTED_SOURCE_TYPES = tuple(EXPECTED_SOURCE_SCALES)


def _completed_results(q, batch_id: Optional[int]):
    if batch_id is not None:
        return q.filter(Result.batch_id == batch_id)
    return q.join(Batch, Result.batch_id == Batch.id).filter(Batch.status == "done")


def _distribution(db: Session, batch_id: Optional[int], column) -> dict:
    q = db.query(column, func.count(Result.id)).filter(column.isnot(None), column != "")
    q = _completed_results(q, batch_id)
    rows = q.group_by(column).all()
    return {k: v for k, v in sorted(rows, key=lambda x: -x[1])}


def _distribution_mentions(db: Session, batch_id: Optional[int], col1, col2) -> dict:
    fusion: dict = {}
    for col in (col1, col2):
        for libelle, n in _distribution(db, batch_id, col).items():
            fusion[libelle] = fusion.get(libelle, 0) + n
    return dict(sorted(fusion.items(), key=lambda kv: -kv[1]))


def _distribution_hierarchy(
    db: Session,
    batch_id: Optional[int],
    pairs,
) -> dict[str, dict[str, int]]:
    """Compte les sous-thèmes sans perdre leur parent de niveau 1.

    Les répartitions historiques ``subthemes*`` restent volontairement plates
    pour préserver le contrat public existant. Cette vue complémentaire porte la
    relation nécessaire au drill-down de l'interface. Elle est calculée depuis
    les couples réellement persistés — corrections humaines comprises — plutôt
    que reconstruite depuis la taxonomie active, qui peut différer de celle du lot.
    """
    hierarchy: dict[str, dict[str, int]] = {}
    for niv1_column, niv2_column in pairs:
        query = db.query(
            niv1_column,
            niv2_column,
            func.count(Result.id),
        ).filter(
            niv1_column.isnot(None), niv1_column != "",
            niv2_column.isnot(None), niv2_column != "",
        )
        query = _completed_results(query, batch_id)
        for niv1, niv2, count in query.group_by(niv1_column, niv2_column).all():
            children = hierarchy.setdefault(niv1, {})
            children[niv2] = children.get(niv2, 0) + count

    sorted_parents = sorted(
        hierarchy.items(),
        key=lambda item: (-sum(item[1].values()), item[0].casefold()),
    )
    return {
        niv1: dict(sorted(children.items(), key=lambda item: (-item[1], item[0].casefold())))
        for niv1, children in sorted_parents
    }


def _theme_sentiment(db: Session, batch_id: Optional[int] = None) -> dict:
    out: dict = {}
    for col_theme, col_sent in (
        (Result.theme1_niv1, Result.theme1_sentiment),
        (Result.theme2_niv1, Result.theme2_sentiment),
    ):
        q = db.query(col_theme, col_sent, func.count(Result.id)).filter(
            col_theme.isnot(None), col_theme != "", col_sent.isnot(None), col_sent != "")
        q = _completed_results(q, batch_id)
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
    return _completed_results(q, batch_id).scalar() or 0


def _n_classified(db: Session, batch_id: Optional[int] = None) -> int:
    """Compte le périmètre réellement classé, dénominateur du taux bi-thème."""
    q = db.query(func.count(Result.id)).filter(
        Result.theme1_niv1.isnot(None), Result.theme1_niv1 != "")
    return _completed_results(q, batch_id).scalar() or 0


# --------------------------------------------------------------------------- #
# Évolution des classifications : un verbatim compte au plus une fois par
# classification, même si une sortie anormale répétait le même thème en rang 1
# et 2. Les parts utilisent le nombre de verbatims de la source comme
# dénominateur ; leur somme peut dépasser 100 % avec les bi-thèmes, ce qui est
# précisément la lecture « toutes mentions » documentée par D37.
# --------------------------------------------------------------------------- #
def _classification_snapshot(db: Session, batch_id: int) -> dict:
    rows = (
        db.query(
            Result.id, Result.source,
            Result.theme1_niv1, Result.theme1_niv2,
            Result.theme2_niv1, Result.theme2_niv2,
        )
        .filter(Result.batch_id == batch_id)
        .all()
    )
    totals: dict[str, int] = {}
    counts: dict[str, dict[str, dict[tuple[str, Optional[str]], int]]] = {
        "niv1": {}, "niv2": {},
    }
    for row in rows:
        source = row.source or "source-inconnue"
        totals[source] = totals.get(source, 0) + 1
        seen: dict[str, set[tuple[str, Optional[str]]]] = {
            "niv1": set(), "niv2": set(),
        }
        for niv1, niv2 in (
            (row.theme1_niv1, row.theme1_niv2),
            (row.theme2_niv1, row.theme2_niv2),
        ):
            if not niv1:
                continue
            seen["niv1"].add((niv1, None))
            if niv2:
                seen["niv2"].add((niv1, niv2))
        for level in ("niv1", "niv2"):
            bucket = counts[level].setdefault(source, {})
            for key in seen[level]:
                bucket[key] = bucket.get(key, 0) + 1

    return {"totals": totals, "counts": counts}


def _ranked_classifications(values: dict[tuple[str, Optional[str]], int]) -> list[tuple]:
    return sorted(
        values.items(),
        key=lambda item: (-item[1], item[0][0].casefold(), (item[0][1] or "").casefold()),
    )


def _classification_level_evolution(
    current_data: dict,
    reference_data: dict,
    reference_exists: bool,
    comparable: bool,
    level: str,
) -> list[dict]:
    out = []
    all_sources = list(EXPECTED_SOURCE_TYPES)
    all_sources.extend(sorted(
        set(current_data["totals"]) - set(EXPECTED_SOURCE_TYPES),
        key=lambda value: value.casefold(),
    ))
    for source in all_sources:
        current_total = current_data["totals"].get(source, 0)
        reference_total = reference_data["totals"].get(source, 0)
        source_comparable = comparable and current_total > 0 and reference_total > 0
        current_values = current_data["counts"][level].get(source, {})
        reference_values = reference_data["counts"][level].get(source, {})
        current_ranked = _ranked_classifications(current_values)
        reference_ranks = {
            key: index for index, (key, _count) in enumerate(
                _ranked_classifications(reference_values), start=1)
        }
        items = []
        for current_rank, (key, current_count) in enumerate(
            current_ranked[:CLASSIFICATION_TOP_N], start=1
        ):
            niv1, niv2 = key
            reference_count = reference_values.get(key, 0)
            current_share = current_count / current_total if current_total else 0.0
            reference_share = (
                reference_count / reference_total if reference_total else 0.0
            )
            reference_rank = reference_ranks.get(key)
            items.append({
                "niv1": niv1,
                "niv2": niv2,
                "label": niv2 if level == "niv2" else niv1,
                "current_rank": current_rank,
                "reference_rank": reference_rank,
                "rank_delta": (
                    reference_rank - current_rank
                    if source_comparable and reference_rank is not None else None
                ),
                "current_count": current_count,
                "reference_count": reference_count if reference_exists else None,
                "count_delta": (
                    current_count - reference_count if source_comparable else None
                ),
                "current_share": round(current_share, 6),
                "reference_share": (
                    round(reference_share, 6) if reference_exists else None
                ),
                "share_delta": (
                    round(current_share - reference_share, 6) if source_comparable else None
                ),
            })
        out.append({
            "source_type": source,
            "availability_status": (
                "available" if current_total > 0 else "source_not_provided"
            ),
            "comparable": source_comparable,
            "reason": (
                None if source_comparable else
                "Source absente du lot courant."
                if current_total == 0 else
                "Source absente du lot de référence."
                if comparable and reference_exists and reference_total == 0 else
                "Aucun lot de référence sélectionné."
                if not reference_exists else
                "Le modèle ou le référentiel diffère entre les lots."
            ),
            "current_verbatim_count": current_total,
            "reference_verbatim_count": (
                reference_total if reference_exists else None
            ),
            "items": items,
        })
    return out


def _classification_evolution(
    db: Session, current: Batch, reference: Optional[Batch]
) -> dict:
    current_data = _classification_snapshot(db, current.id)
    reference_data = (
        _classification_snapshot(db, reference.id)
        if reference is not None
        else {"totals": {}, "counts": {"niv1": {}, "niv2": {}}}
    )
    comparable = bool(
        reference is not None
        and current.model_label
        and current.model_label == reference.model_label
    )
    if reference is None:
        reason = "Aucun lot de référence sélectionné."
    elif not comparable:
        reason = "Le modèle ou le référentiel diffère entre les lots."
    else:
        reason = None
    return {
        "unit": "verbatim",
        "angle": "all_mentions",
        "denominator": "source_verbatims",
        "top_n": CLASSIFICATION_TOP_N,
        "comparable": comparable,
        "reason": reason,
        "levels": {
            "niv1": _classification_level_evolution(
                current_data, reference_data, reference is not None, comparable, "niv1"),
            "niv2": _classification_level_evolution(
                current_data, reference_data, reference is not None, comparable, "niv2"),
        },
    }


# --------------------------------------------------------------------------- #
# Satisfaction : une SurveyResponse = une voix
# --------------------------------------------------------------------------- #
def _response_rows(db: Session, batch_id: Optional[int]) -> list[SurveyResponse]:
    q = db.query(SurveyResponse)
    if batch_id is not None:
        q = q.filter(SurveyResponse.batch_id == batch_id)
    else:
        q = q.join(Batch, SurveyResponse.batch_id == Batch.id).filter(Batch.status == "done")
    return q.all()


def _legacy_sources(db: Session, batch_id: Optional[int]) -> dict[str, int]:
    """Compte les verbatims historiques sans réponse liée, sans inventer de répondant."""
    q = db.query(Result.source, func.count(Result.id)).filter(Result.survey_response_id.is_(None))
    q = _completed_results(q, batch_id)
    return {(source or "source-inconnue"): int(n) for source, n in q.group_by(Result.source).all()}


def _valid_rating(row: SurveyResponse) -> bool:
    return (
        not row.rating_invalid
        and row.satisfaction_native is not None
        and SATISFACTION_MIN <= row.satisfaction_native <= row.satisfaction_scale_max
    )


def _period(rows: list[SurveyResponse]) -> dict:
    """Décrit la période réellement couverte par les réponses d'une source.

    La date technique de création du lot est volontairement absente de ce
    contrat : une relance ou un upload tardif ne doit pas déplacer la période
    analysée.
    """
    dated = [r.response_date for r in rows if r.response_date is not None]
    return {
        "start": min(dated).isoformat() if dated else None,
        "end": max(dated).isoformat() if dated else None,
        "dated_respondent_count": len(dated),
        "undated_respondent_count": len(rows) - len(dated),
    }


def _segment(rows: list[SurveyResponse], client_status: str) -> dict:
    selected = [r for r in rows if r.client_status == client_status]
    rated = [r for r in selected if _valid_rating(r)]
    mean_native = (sum(r.satisfaction_native for r in rated) / len(rated)) if rated else None
    scales = {r.satisfaction_scale_max for r in selected}
    scale = next(iter(scales)) if len(scales) == 1 else None
    return {
        "client_status": client_status,
        "respondent_count": len(selected),
        "rated_respondent_count": len(rated),
        "unrated_respondent_count": sum(
            r.satisfaction_native is None and not r.rating_invalid for r in selected),
        "invalid_rating_count": sum(
            r.rating_invalid or (r.satisfaction_native is not None and not _valid_rating(r))
            for r in selected),
        "mean_native": round(mean_native, 2) if mean_native is not None else None,
        "mean_on_10": round(mean_native / scale * 10, 2)
        if mean_native is not None and scale else None,
    }


def _empty_segment(client_status: str) -> dict:
    """Segment explicitement présent mais sans répondant dans le périmètre."""
    return {
        "client_status": client_status,
        "respondent_count": 0,
        "rated_respondent_count": 0,
        "unrated_respondent_count": 0,
        "invalid_rating_count": 0,
        "mean_native": None,
        "mean_on_10": None,
    }


def _unavailable_source(source: str, legacy_count: int) -> dict:
    """Décrit une source attendue absente sans fabriquer une mesure à zéro."""
    historical = legacy_count > 0
    return {
        "source_type": source,
        "availability_status": (
            "historical_unavailable" if historical else "source_not_provided"
        ),
        "native_scale_min": SATISFACTION_MIN,
        "native_scale_max": EXPECTED_SOURCE_SCALES.get(source),
        # Zéro décrit ici la couverture du lot, pas une note. Sur un lot
        # historique, le nombre de répondants reste inconnu car seuls les
        # verbatims ont été conservés.
        "respondent_count": None if historical else 0,
        "rated_respondent_count": 0,
        "unrated_respondent_count": None if historical else 0,
        "invalid_rating_count": 0,
        "mean_native": None,
        "mean_on_10": None,
        "native_distribution": {},
        "by_client_status": (
            [] if historical else [_empty_segment(status) for status in CLIENT_STATUSES]
        ),
        "period": {
            "start": None,
            "end": None,
            "dated_respondent_count": 0,
            "undated_respondent_count": None if historical else 0,
        },
        "native_detail_available": False,
        "historical_verbatim_count": legacy_count,
        "availability_message": (
            "Détail natif indisponible : retraitement du lot requis."
            if historical else
            "Aucune donnée reçue pour cette source dans ce lot."
        ),
    }


def _satisfaction(db: Session, batch_id: Optional[int] = None) -> dict:
    rows = _response_rows(db, batch_id)
    legacy = _legacy_sources(db, batch_id)
    grouped: dict[str, list[SurveyResponse]] = {}
    for row in rows:
        grouped.setdefault(row.source_type, []).append(row)

    source_order = {source: index for index, source in enumerate(EXPECTED_SOURCE_TYPES)}
    by_source = []
    sources = set(EXPECTED_SOURCE_TYPES) | set(grouped) | set(legacy)
    for source in sorted(sources, key=lambda s: (source_order.get(s, 99), s)):
        source_rows = grouped.get(source, [])
        if not source_rows:
            by_source.append(_unavailable_source(source, legacy.get(source, 0)))
            continue

        scales = {r.satisfaction_scale_max for r in source_rows}
        scale = next(iter(scales)) if len(scales) == 1 else None
        rated = [r for r in source_rows if _valid_rating(r)]
        mean_native = (sum(r.satisfaction_native for r in rated) / len(rated)) if rated else None
        if scale is None:
            mean_native = None
        distribution: dict[str, int] = {}
        for row in rated:
            key = str(row.satisfaction_native)
            distribution[key] = distribution.get(key, 0) + 1
        by_source.append({
            "source_type": source,
            "availability_status": (
                "inconsistent_scale" if scale is None else
                "partial_history" if legacy.get(source) else
                "available"
            ),
            "native_scale_min": SATISFACTION_MIN,
            "native_scale_max": scale,
            "respondent_count": len(source_rows),
            "rated_respondent_count": len(rated),
            "unrated_respondent_count": sum(
                r.satisfaction_native is None and not r.rating_invalid for r in source_rows),
            "invalid_rating_count": sum(
                r.rating_invalid or (r.satisfaction_native is not None and not _valid_rating(r))
                for r in source_rows),
            "mean_native": round(mean_native, 2) if mean_native is not None else None,
            "mean_on_10": round(mean_native / scale * 10, 2)
            if mean_native is not None and scale else None,
            "native_distribution": dict(sorted(distribution.items())),
            "by_client_status": [_segment(source_rows, s) for s in CLIENT_STATUSES],
            "period": _period(source_rows),
            "native_detail_available": scale is not None,
            "historical_verbatim_count": legacy.get(source, 0),
            "availability_message": (
                "Échelles natives incohérentes pour cette source : moyenne indisponible."
                if scale is None else
                "Périmètre partiel : des verbatims historiques exigent un retraitement."
                if legacy.get(source) else None),
        })

    rated_all = [r for r in rows if _valid_rating(r)]
    mean_on_10 = (
        sum(r.satisfaction_native / r.satisfaction_scale_max * 10 for r in rated_all) / len(rated_all)
        if rated_all else None
    )
    return {
        "unit": "respondent",
        "display_scale_max": 10,
        "expected_source_types": list(EXPECTED_SOURCE_TYPES),
        "by_source": by_source,
        "global": {
            "scope": (
                "Répondants avec au moins un verbatim analysé, lots terminés uniquement."
                if batch_id is None else
                "Répondants de ce lot avec au moins un verbatim analysé."
            ),
            "respondent_count": len(rows),
            "rated_respondent_count": len(rated_all),
            "mean_on_10": round(mean_on_10, 2) if mean_on_10 is not None else None,
        },
        "historical_data_unavailable": bool(legacy),
    }


def _default_reference_batch(db: Session, current: Batch) -> Optional[Batch]:
    """Retourne le dernier lot métier antérieur partageant au moins une source.

    Un lot sans date métier n'a pas de référence automatique. Parmi les lots
    terminés, on retient celui dont la dernière réponse précède strictement la
    première réponse du lot courant. Un retraitement de la même période ne peut
    donc pas être choisi silencieusement comme « période précédente ».
    """
    current_rows = _response_rows(db, current.id)
    current_dates = [r.response_date for r in current_rows if r.response_date is not None]
    current_sources = {r.source_type for r in current_rows}
    if not current_dates or not current_sources:
        return None
    current_start = min(current_dates)
    candidates = (
        db.query(SurveyResponse.batch_id, func.max(SurveyResponse.response_date).label("period_end"))
        .join(Batch, SurveyResponse.batch_id == Batch.id)
        .filter(
            Batch.status == "done",
            Batch.id != current.id,
            SurveyResponse.source_type.in_(current_sources),
            SurveyResponse.response_date.isnot(None),
        )
        .group_by(SurveyResponse.batch_id)
        .having(func.max(SurveyResponse.response_date) < current_start)
        .order_by(func.max(SurveyResponse.response_date).desc(), SurveyResponse.batch_id.desc())
        .first()
    )
    return db.get(Batch, candidates.batch_id) if candidates else None


def _metric(current: float, reference: float, *, unit: str) -> dict:
    delta = current - reference
    return {
        "current": current,
        "reference": reference,
        "delta": round(delta, 4),
        "unit": unit,
    }


def _source_comparison(current: dict, reference: Optional[dict]) -> dict:
    """Compare deux agrégats de satisfaction ou explique pourquoi c'est impossible."""
    base = {
        "source_type": current["source_type"],
        "comparable": False,
        "reason": None,
        "warning": None,
        "current_period": current["period"],
        "reference_period": reference["period"] if reference else None,
        "current_mean_on_10": current["mean_on_10"],
        "reference_mean_on_10": reference["mean_on_10"] if reference else None,
        "delta_on_10": None,
        "current_rated_respondent_count": current["rated_respondent_count"],
        "reference_rated_respondent_count": reference["rated_respondent_count"] if reference else 0,
        "by_client_status": [],
    }
    if reference is None:
        base["reason"] = "Source absente du lot de référence."
        return base
    if current["availability_status"] == "source_not_provided":
        base["reason"] = "Source absente du lot courant."
        return base
    if reference["availability_status"] == "source_not_provided":
        base["reason"] = "Source absente du lot de référence."
        return base
    if not current["native_detail_available"] or not reference["native_detail_available"]:
        base["reason"] = "Détail natif indisponible : retraitement requis."
        return base
    if current["native_scale_max"] != reference["native_scale_max"]:
        base["reason"] = "Échelles natives différentes entre les deux lots."
        return base
    if current["mean_on_10"] is None or reference["mean_on_10"] is None:
        base["reason"] = "Aucune note valide dans l'une des deux périodes."
        return base
    if not current["period"]["start"] or not reference["period"]["start"]:
        base["reason"] = "Période métier indisponible : dates source absentes."
        return base

    base["comparable"] = True
    base["delta_on_10"] = round(current["mean_on_10"] - reference["mean_on_10"], 2)
    if (current["period"]["undated_respondent_count"] or
            reference["period"]["undated_respondent_count"]):
        base["warning"] = "Période partielle : certaines réponses n'ont pas de date source."
    if not (current["period"]["start"] > reference["period"]["end"] or
            reference["period"]["start"] > current["period"]["end"]):
        base["warning"] = "Les périodes se chevauchent ; interpréter l'évolution avec prudence."

    ref_segments = {s["client_status"]: s for s in reference["by_client_status"]}
    for segment in current["by_client_status"]:
        ref_segment = ref_segments.get(segment["client_status"])
        ref_mean = ref_segment["mean_on_10"] if ref_segment else None
        base["by_client_status"].append({
            "client_status": segment["client_status"],
            "current_mean_on_10": segment["mean_on_10"],
            "reference_mean_on_10": ref_mean,
            "delta_on_10": (
                round(segment["mean_on_10"] - ref_mean, 2)
                if segment["mean_on_10"] is not None and ref_mean is not None else None
            ),
            "current_rated_respondent_count": segment["rated_respondent_count"],
            "reference_rated_respondent_count": (
                ref_segment["rated_respondent_count"] if ref_segment else 0),
        })
    return base


def _comparison(db: Session, current: Batch, reference: Batch) -> dict:
    current_sat = _satisfaction(db, current.id)
    reference_sat = _satisfaction(db, reference.id)
    references = {s["source_type"]: s for s in reference_sat["by_source"]}

    current_bi = _n_bi_themes(db, current.id)
    reference_bi = _n_bi_themes(db, reference.id)
    current_classified = _n_classified(db, current.id)
    reference_classified = _n_classified(db, reference.id)
    current_signals = _signal_counts(db, current.id)
    reference_signals = _signal_counts(db, reference.id)
    model_compatible = bool(current.model_label and current.model_label == reference.model_label)
    review_compatible = model_compatible and current.seuil_revue == reference.seuil_revue

    signal_metrics = {}
    for name in ("rupture", "churn", "insatisfaction"):
        current_rate = current_signals[name] / current.n_total if current.n_total else 0.0
        reference_rate = reference_signals[name] / reference.n_total if reference.n_total else 0.0
        signal_metrics[name] = _metric(current_rate, reference_rate, unit="ratio")

    return {
        "reference_batch": {
            "id": reference.id,
            "label": reference.label,
            "model_label": reference.model_label,
        },
        "satisfaction": {
            "by_source": [
                _source_comparison(source, references.get(source["source_type"]))
                for source in current_sat["by_source"]
            ],
        },
        "lot_metrics": {
            "volume": _metric(current.n_total, reference.n_total, unit="count"),
            "review_rate": {
                **_metric(
                    current.n_review / current.n_total if current.n_total else 0.0,
                    reference.n_review / reference.n_total if reference.n_total else 0.0,
                    unit="ratio",
                ),
                "comparable": review_compatible,
                "reason": None if review_compatible else
                    "Le modèle ou le seuil de revue diffère entre les lots.",
            },
            "bi_theme_rate": {
                **_metric(
                    current_bi / current_classified if current_classified else 0.0,
                    reference_bi / reference_classified if reference_classified else 0.0,
                    unit="ratio",
                ),
                "comparable": model_compatible,
                "reason": None if model_compatible else
                    "Le modèle diffère entre les lots.",
            },
            "signal_rates": {
                name: {
                    **metric,
                    "comparable": model_compatible,
                    "reason": None if model_compatible else
                        "Le modèle diffère entre les lots.",
                }
                for name, metric in signal_metrics.items()
            },
        },
    }


@router.get("/batches/{batch_id}/kpi")
def batch_kpi(batch_id: int, reference_batch_id: Optional[int] = None,
              db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    n_bi = _n_bi_themes(db, batch_id)
    n_classes = _n_classified(db, batch_id)
    reference = None
    reference_mode = "automatic"
    if reference_batch_id is not None:
        reference_mode = "explicit"
        if reference_batch_id == batch.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Un lot ne peut pas être comparé à lui-même.")
        reference = db.get(Batch, reference_batch_id)
        if reference is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Lot de référence introuvable")
        if reference.status != "done":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Le lot de référence doit être terminé.")
    elif batch.status == "done":
        reference = _default_reference_batch(db, batch)

    return {
        "batch_id": batch.id, "label": batch.label, "status": batch.status,
        "model_label": batch.model_label, "n_total": batch.n_total,
        "n_processed": batch.n_processed, "n_review": batch.n_review,
        "review_rate": (batch.n_review / batch.n_total) if batch.n_total else 0.0,
        "n_errors": batch.n_errors, "duration_s": batch.duration_s,
        "themes": _distribution(db, batch_id, Result.theme1_niv1),
        "subthemes": _distribution(db, batch_id, Result.theme1_niv2),
        "themes_secondaires": _distribution(db, batch_id, Result.theme2_niv1),
        "subthemes_secondaires": _distribution(db, batch_id, Result.theme2_niv2),
        "themes_mentions": _distribution_mentions(db, batch_id, Result.theme1_niv1, Result.theme2_niv1),
        "subthemes_mentions": _distribution_mentions(db, batch_id, Result.theme1_niv2, Result.theme2_niv2),
        "theme_hierarchy": {
            "principal": _distribution_hierarchy(
                db, batch_id, ((Result.theme1_niv1, Result.theme1_niv2),)),
            "mentions": _distribution_hierarchy(
                db, batch_id,
                (
                    (Result.theme1_niv1, Result.theme1_niv2),
                    (Result.theme2_niv1, Result.theme2_niv2),
                ),
            ),
            "secondaire": _distribution_hierarchy(
                db, batch_id, ((Result.theme2_niv1, Result.theme2_niv2),)),
        },
        "n_bi_themes": n_bi,
        "taux_bi_themes": (n_bi / n_classes) if n_classes else 0.0,
        "sentiments": _distribution(db, batch_id, Result.theme1_sentiment),
        "sentiments_secondaires": _distribution(db, batch_id, Result.theme2_sentiment),
        "sources": _distribution(db, batch_id, Result.source),
        "signals": _signal_counts(db, batch_id),
        "theme_sentiment": _theme_sentiment(db, batch_id),
        "satisfaction": _satisfaction(db, batch_id),
        "classification_evolution": _classification_evolution(db, batch, reference),
        "comparison": (
            {**_comparison(db, batch, reference), "reference_mode": reference_mode}
            if reference is not None else None
        ),
    }


@router.get("/kpi/volumetry")
def volumetry(db: Session = Depends(get_db)):
    batches = db.query(Batch).filter(Batch.status == "done").order_by(Batch.created_at).all()
    series = []
    for batch in batches:
        series.append({
            "id": batch.id, "label": batch.label,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "n_total": batch.n_total, "n_review": batch.n_review,
            "review_rate": (batch.n_review / batch.n_total) if batch.n_total else 0.0,
            "signals": _signal_counts(db, batch.id),
            "n_bi_themes": _n_bi_themes(db, batch.id),
        })
    return {
        "n_batches": len(batches), "total_verbatims": sum(b.n_total for b in batches),
        "series": series,
        "global_themes": _distribution(db, None, Result.theme1_niv1),
        "global_themes_mentions": _distribution_mentions(db, None, Result.theme1_niv1, Result.theme2_niv1),
        "global_themes_secondaires": _distribution(db, None, Result.theme2_niv1),
        "n_bi_themes": _n_bi_themes(db, None),
        "theme_sentiment": _theme_sentiment(db, None),
        "satisfaction": _satisfaction(db, None),
    }


@router.get("/kpi/model")
def model_kpi(db: Session = Depends(get_db)):
    active = db.query(ModelVersion).filter_by(is_active=True).first()
    if active is None:
        return {"active": None}
    return {"active": {
        "label": active.label, "kind": active.kind,
        "available": active.available, "metrics": active.metrics,
    }}
