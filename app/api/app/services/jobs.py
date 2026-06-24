"""File de jobs (RQ/Redis). L'API enfile des tâches résolues par le worker.

Les tâches sont référencées par leur **chemin pointé** (string), car l'API
n'importe pas le code du worker (images séparées).
"""
from __future__ import annotations

import logging

from redis import Redis
from rq import Queue

from ..core.config import settings

logger = logging.getLogger(__name__)


def get_queue() -> Queue:
    connection = Redis.from_url(settings.redis_url)
    return Queue(settings.job_queue, connection=connection)


def enqueue_batch(batch_id: int) -> str:
    job = get_queue().enqueue(
        "worker.tasks.process_batch_job", batch_id, job_timeout=settings.job_timeout_seconds
    )
    logger.info("Lot %s enfilé (job %s)", batch_id, job.id)
    return job.id


def enqueue_registry_sync() -> str:
    job = get_queue().enqueue("worker.tasks.sync_registry_job", job_timeout=600)
    return job.id


def enqueue_comparison(run_id: int) -> str:
    job = get_queue().enqueue(
        "worker.tasks.run_comparison_job", run_id, job_timeout=settings.job_timeout_seconds
    )
    logger.info("Comparaison %s enfilée (job %s)", run_id, job.id)
    return job.id
