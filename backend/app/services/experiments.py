from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.errors import Conflict, NotFound, Unprocessable
from ..db.models import Experiment, ModelRecord
from ..db.session import Database
from ..ml.errors import MLError
from ..ml.pipeline import TrainConfig, train_experiment
from ..ml.tasks import infer_task
from ..ml.tracking import jsonable, new_id, save_bundle
from .audit import record_audit
from .datasets import dataset_frame, get_dataset
from .retention import utcnow

logger = logging.getLogger(__name__)

CONFIG_FIELDS = ("target", "task", "seed", "test_size", "val_size", "model_names", "exclude_columns", "positive_label")


def create_experiment(db: Session, settings: Settings, jobs, payload: dict[str, Any], actor: str) -> Experiment:
    ds = get_dataset(db, payload["dataset_id"])
    target = payload["target"]
    if target not in {c["name"] for c in ds.profile_json["columns"]}:
        raise Unprocessable(f"Target column '{target[:60]}' is not in the dataset.", code="target_not_found")
    # Fail fast (HTTP 422) on unsupported targets instead of failing later in the background.
    df = dataset_frame(settings, ds)
    infer_task(df[target], payload.get("task"))
    exp = Experiment(
        id=new_id("exp"),
        dataset_id=ds.id,
        target=target,
        task=payload.get("task"),
        status="queued",
        progress=0.0,
        stage="queued",
        seed=payload["seed"],
        dataset_fingerprint=ds.sha256,
        config_json={k: payload.get(k) for k in CONFIG_FIELDS},
        created_at=utcnow(),
    )
    db.add(exp)
    record_audit(db, actor, "experiment.create", "experiment", exp.id, {"dataset_id": ds.id, "target": target})
    db.commit()
    jobs.submit_training(exp.id)
    return exp


def get_experiment(db: Session, experiment_id: str) -> Experiment:
    exp = db.get(Experiment, experiment_id)
    if exp is None:
        raise NotFound("Experiment not found.")
    return exp


def require_summary(exp: Experiment) -> dict[str, Any]:
    if exp.status == "failed":
        raise Conflict(exp.error_message or "The experiment failed.", code="experiment_failed")
    if exp.status != "succeeded" or exp.summary_json is None:
        raise Conflict("The experiment has not finished yet.", code="experiment_not_ready")
    return exp.summary_json


def mark_interrupted(db: Database) -> int:
    with db.session() as s:
        result = s.execute(
            update(Experiment)
            .where(Experiment.status.in_(("queued", "running")))
            .values(status="failed", stage="interrupted", error_message="The server restarted while this experiment was running. Please run it again.", finished_at=utcnow())
        )
        return int(result.rowcount or 0)


def _set_progress(db: Database, experiment_id: str, stage: str, fraction: float) -> None:
    with db.session() as s:
        s.execute(update(Experiment).where(Experiment.id == experiment_id).values(stage=stage[:100], progress=min(max(fraction, 0.0), 1.0)))


def _fail(db: Database, experiment_id: str, message: str) -> None:
    with db.session() as s:
        s.execute(update(Experiment).where(Experiment.id == experiment_id).values(status="failed", stage="failed", error_message=message[:500], finished_at=utcnow()))


def run_training_job(db: Database, settings: Settings, experiment_id: str) -> None:
    """Runs in a worker thread. Opens its own short-lived sessions."""
    try:
        with db.session() as s:
            exp = s.get(Experiment, experiment_id)
            if exp is None:
                return
            exp.status, exp.started_at, exp.stage = "running", utcnow(), "starting"
            config = dict(exp.config_json)
            ds = exp.dataset
            fingerprint = exp.dataset_fingerprint
            df = dataset_frame(settings, ds)
        cfg = TrainConfig(**{k: v for k, v in config.items() if v is not None}, n_jobs=1)
        result = train_experiment(df, cfg, dataset_fingerprint=fingerprint, progress=lambda stage, frac: _set_progress(db, experiment_id, stage, frac))
        model_id = new_id("mdl")
        path, digest = save_bundle(result.bundle, settings.models_dir, model_id)
        with db.session() as s:
            exp = s.get(Experiment, experiment_id)
            if exp is None:  # deleted while training
                path.unlink(missing_ok=True)
                return
            exp.status, exp.stage, exp.progress = "succeeded", "done", 1.0
            exp.task = result.summary["task"]
            exp.summary_json = result.summary
            exp.finished_at = utcnow()
            s.add(
                ModelRecord(
                    id=model_id,
                    experiment_id=experiment_id,
                    name=result.bundle.metadata["model_name"],
                    task=result.summary["task"],
                    target=result.summary["target"],
                    artifact_filename=path.name,
                    artifact_sha256=digest,
                    metadata_json=jsonable(result.bundle.metadata),
                    created_at=utcnow(),
                )
            )
            record_audit(s, "training-job", "experiment.succeeded", "experiment", experiment_id, {"model_id": model_id})
    except MLError as exc:
        logger.info("training rejected", extra={"experiment_id": experiment_id, "code": exc.code})
        _fail(db, experiment_id, exc.message)
    except Exception:  # noqa: BLE001 - never leak internals to clients
        logger.exception("training failed", extra={"experiment_id": experiment_id})
        _fail(db, experiment_id, f"Training failed unexpectedly (reference {experiment_id}). Check the server logs.")
