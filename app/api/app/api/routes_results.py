"""Endpoints des résultats d'un lot : liste filtrable + export CSV/XLSX."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from ..schemas.result import ResultOut, ResultsResponse
from common.models import Batch, Result

router = APIRouter(prefix="/api/batches", tags=["results"], dependencies=[Depends(get_current_user)])

# Colonnes modèle exportées (noms EXACTS du format POC) -> attribut ORM.
_MODEL_COLUMNS = [
    ("verbatim_analysé", "verbatim_analyse"),
    ("nb_themes", "nb_themes"),
    ("theme1_niv1", "theme1_niv1"),
    ("theme1_niv2", "theme1_niv2"),
    ("theme1_sentiment", "theme1_sentiment"),
    ("theme1_score_confiance", "theme1_score"),
    ("theme2_niv1", "theme2_niv1"),
    ("theme2_niv2", "theme2_niv2"),
    ("theme2_sentiment", "theme2_sentiment"),
    ("theme2_score_confiance", "theme2_score"),
    ("signal_rupture_client", "signal_rupture"),
    ("signal_churn", "signal_churn"),
    ("signal_insatisfaction_forte", "signal_insatisfaction"),
    ("confidence_globale", "confidence_globale"),
    ("revue_humaine_requise", "revue_requise"),
]


def _get_batch_or_404(db: Session, batch_id: int) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    return batch


def _like_escape(s: str) -> str:
    """Échappe les métacaractères LIKE (%, _) pour une recherche « contient »
    littérale : taper « 50% » ou « e_carte » ne doit pas se comporter en joker."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_filters(query, niv1, sentiment, revue, rupture, churn, insatisfaction, q):
    if niv1:
        # Recherche « contient » sur le thème (niv.1 OU niv.2), pas une égalité
        # exacte : taper « Programme » doit matcher « Programme de fidélité ».
        like = f"%{_like_escape(niv1)}%"
        query = query.filter(or_(Result.theme1_niv1.ilike(like, escape="\\"),
                                 Result.theme1_niv2.ilike(like, escape="\\")))
    if sentiment:
        query = query.filter(Result.theme1_sentiment == sentiment)
    if revue is not None:
        query = query.filter(Result.revue_requise == revue)
    if rupture:
        query = query.filter(Result.signal_rupture == True)  # noqa: E712
    if churn:
        query = query.filter(Result.signal_churn == True)  # noqa: E712
    if insatisfaction:
        query = query.filter(Result.signal_insatisfaction == True)  # noqa: E712
    if q:
        query = query.filter(Result.verbatim_analyse.ilike(f"%{_like_escape(q)}%", escape="\\"))
    return query


@router.get("/{batch_id}/results", response_model=ResultsResponse)
def list_results(
    batch_id: int,
    db: Session = Depends(get_db),
    niv1: Optional[str] = None,
    sentiment: Optional[str] = None,
    revue: Optional[bool] = None,
    rupture: bool = False,
    churn: bool = False,
    insatisfaction: bool = False,
    q: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    _get_batch_or_404(db, batch_id)
    base = db.query(Result).filter(Result.batch_id == batch_id)
    base = _apply_filters(base, niv1, sentiment, revue, rupture, churn, insatisfaction, q)
    total = base.with_entities(func.count(Result.id)).scalar() or 0
    items = base.order_by(Result.row_index).offset(offset).limit(limit).all()
    return ResultsResponse(total=total, limit=limit, offset=offset,
                           items=[ResultOut.model_validate(r) for r in items])


def _enriched_rows(results: list[Result]):
    """Construit (entêtes, lignes) du fichier enrichi : colonnes d'origine + modèle."""
    orig_keys: list[str] = []
    seen = set()
    for r in results:
        for k in (r.original_columns or {}):
            if k not in seen:
                seen.add(k)
                orig_keys.append(k)

    headers = ["source"] + orig_keys + [name for name, _ in _MODEL_COLUMNS]
    rows = []
    for r in results:
        oc = r.original_columns or {}
        row = [r.source or ""] + [oc.get(k, "") for k in orig_keys]
        for _, attr in _MODEL_COLUMNS:
            val = getattr(r, attr)
            row.append("" if val is None else val)
        rows.append(row)
    return headers, rows


@router.get("/{batch_id}/export")
def export_results(
    batch_id: int,
    format: str = "csv",
    db: Session = Depends(get_db),
    niv1: Optional[str] = None,
    sentiment: Optional[str] = None,
    revue: Optional[bool] = None,
    rupture: bool = False,
    churn: bool = False,
    insatisfaction: bool = False,
    q: Optional[str] = None,
):
    """Export enrichi. Les mêmes filtres que la liste sont honorés : si des
    filtres sont passés, l'export ne contient QUE les lignes correspondantes."""
    batch = _get_batch_or_404(db, batch_id)
    query = db.query(Result).filter(Result.batch_id == batch_id)
    query = _apply_filters(query, niv1, sentiment, revue, rupture, churn, insatisfaction, q)
    results = query.order_by(Result.row_index).all()
    headers, rows = _enriched_rows(results)
    stem = f"classifications_{batch.label}".replace(" ", "_")

    if format == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "classifications"
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )

    # CSV (utf-8-sig pour Excel FR)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
    )
