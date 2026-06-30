"""Test à la volée : prédiction immédiate d'un verbatim unique via le worker."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.security import get_current_user
from ..schemas.result import PredictRequest
from ..services.jobs import get_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["predict"], dependencies=[Depends(get_current_user)])

_TIMEOUT_S = 20
_POLL_S = 0.2


@router.post("/predict")
def predict(payload: PredictRequest):
    """Enfile une prédiction unitaire et attend (court) son résultat."""
    queue = get_queue()
    try:
        job = queue.enqueue("worker.tasks.predict_one_job", payload.text, payload.satisfaction,
                            payload.model_id, job_timeout=120)
    except Exception as exc:  # Redis indisponible
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"File de traitement indisponible : {exc}")

    deadline = time.time() + _TIMEOUT_S
    while time.time() < deadline:
        st = job.get_status(refresh=True)
        if st == "finished":
            return job.result
        if st == "failed":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Échec de la prédiction.")
        time.sleep(_POLL_S)
    raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail="Délai dépassé (worker occupé ou indisponible).")
