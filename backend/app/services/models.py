from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.errors import NotFound
from ..db.models import ModelRecord, PredictionEvent
from ..ml.pipeline import ModelBundle
from ..ml.tracking import jsonable, load_bundle, new_id
from ..security.files import resolve_inside
from .audit import record_audit
from .retention import utcnow

logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _load_cached(path: str, sha256: str) -> ModelBundle:
    return load_bundle(path, sha256)


def clear_bundle_cache() -> None:
    _load_cached.cache_clear()


def get_model(db: Session, model_id: str) -> ModelRecord:
    model = db.get(ModelRecord, model_id)
    if model is None:
        raise NotFound("Model not found.")
    return model


def get_bundle(settings: Settings, model: ModelRecord) -> ModelBundle:
    try:
        path = resolve_inside(settings.models_dir, model.artifact_filename)
    except ValueError as exc:
        raise NotFound("Model artifact is unavailable.") from exc
    return _load_cached(str(path), model.artifact_sha256)


def _store_event(db: Session, model: ModelRecord, n_records: int, digest: str, summary: dict[str, Any], actor: str) -> None:
    db.add(PredictionEvent(id=new_id("pred"), model_id=model.id, n_records=n_records, input_sha256=digest, summary_json=jsonable(summary), created_at=utcnow()))
    record_audit(db, actor, "model.predict", "model", model.id, {"n_records": n_records})
    db.commit()


def record_prediction(db: Session, model: ModelRecord, records: list[dict[str, Any]], result: dict[str, Any], actor: str) -> None:
    """Store a hash of the request and an aggregate summary. Input values are never persisted."""
    digest = hashlib.sha256(json.dumps(records, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    preds = result["predictions"]
    summary: dict[str, Any] = {"issues": len(result["issues"])}
    if model.task == "regression":
        summary["mean_prediction"] = sum(p["prediction"] for p in preds) / len(preds)
    else:
        summary["predicted_classes"] = dict(Counter(p["prediction"] for p in preds))
        summary["low_confidence"] = sum(1 for p in preds if p["low_confidence"])
    _store_event(db, model, len(records), digest, summary, actor)


def record_csv_prediction(db: Session, model: ModelRecord, content: bytes, out: pd.DataFrame, actor: str) -> None:
    """Same as ``record_prediction`` for a CSV upload: only the file hash and aggregates are kept."""
    summary: dict[str, Any] = {}
    if model.task == "regression":
        summary["mean_prediction"] = float(out["prediction"].mean())
    else:
        summary["predicted_classes"] = {str(k): int(v) for k, v in out["prediction"].value_counts().items()}
        summary["low_confidence"] = int(out["low_confidence"].sum()) if "low_confidence" in out.columns else 0
    _store_event(db, model, int(len(out)), hashlib.sha256(content).hexdigest(), summary, actor)


def delete_model(db: Session, settings: Settings, model: ModelRecord, actor: str) -> None:
    name, model_id = model.artifact_filename, model.id
    db.delete(model)
    record_audit(db, actor, "model.delete", "model", model_id)
    db.commit()
    try:
        resolve_inside(settings.models_dir, name).unlink(missing_ok=True)
    except (ValueError, OSError):
        logger.warning("could not remove model artifact", extra={"file": name})
    clear_bundle_cache()
