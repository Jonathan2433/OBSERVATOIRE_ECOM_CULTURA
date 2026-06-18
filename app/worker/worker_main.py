"""Bootstrap du worker RQ : se connecte à Redis et consomme la file 'default'."""
from __future__ import annotations

import logging
import os

from redis import Redis
from rq import Queue, Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("worker")

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUES = ["default"]


def _sync_registry_safe() -> None:
    """Synchronise le registre des modèles au démarrage (non bloquant)."""
    try:
        from .config_worker import build_worker_cfg
        from .model_registry import sync_registry

        sync_registry(build_worker_cfg())
        logger.info("Registre des modèles synchronisé.")
    except Exception as exc:  # pragma: no cover
        logger.warning("Synchronisation du registre ignorée au démarrage : %s", exc)


def main() -> None:
    logger.info("Worker en démarrage — Redis=%s, files=%s", REDIS_URL, QUEUES)
    connection = Redis.from_url(REDIS_URL)
    # Vérifie la connectivité avant de boucler.
    connection.ping()
    _sync_registry_safe()
    try:
        from .tasks import reconcile_orphan_batches
        rec = reconcile_orphan_batches()
        if rec.get("reconciled"):
            logger.info("Lots orphelins (interrompus) repassés en échec : %s", rec["reconciled"])
    except Exception as exc:  # pragma: no cover
        logger.warning("Réconciliation des lots orphelins ignorée : %s", exc)
    try:
        from .tasks import purge_old_data_job
        res = purge_old_data_job()
        if res.get("batches"):
            logger.info("Purge rétention au démarrage : %s lot(s) supprimé(s).", res["batches"])
    except Exception as exc:  # pragma: no cover
        logger.warning("Purge de rétention au démarrage ignorée : %s", exc)
    logger.info("Connexion Redis OK. En attente de jobs...")
    worker = Worker([Queue(name, connection=connection) for name in QUEUES], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
