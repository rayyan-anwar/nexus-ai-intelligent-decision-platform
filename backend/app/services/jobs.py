from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from ..core.config import Settings
from ..db.session import Database
from .experiments import run_training_job

logger = logging.getLogger(__name__)


class JobRunner:
    """Simple in-process job queue. Training never blocks the API thread.

    State lives in the database, so a restart marks unfinished work as failed (see ``mark_interrupted``).
    For multi-instance deployments replace this class with a real queue (documented in docs/architecture.md).
    """

    def __init__(self, db: Database, settings: Settings):
        self._db = db
        self._settings = settings
        self._pool = ThreadPoolExecutor(max_workers=settings.training_workers, thread_name_prefix="nexus-train")

    def submit_training(self, experiment_id: str) -> None:
        self._pool.submit(self._run, experiment_id)

    def _run(self, experiment_id: str) -> None:
        try:
            run_training_job(self._db, self._settings, experiment_id)
        except Exception:  # noqa: BLE001
            logger.exception("job runner error", extra={"experiment_id": experiment_id})

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
