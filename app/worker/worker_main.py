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


def main() -> None:
    logger.info("Worker en démarrage — Redis=%s, files=%s", REDIS_URL, QUEUES)
    connection = Redis.from_url(REDIS_URL)
    # Vérifie la connectivité avant de boucler.
    connection.ping()
    logger.info("Connexion Redis OK. En attente de jobs...")
    worker = Worker([Queue(name, connection=connection) for name in QUEUES], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
