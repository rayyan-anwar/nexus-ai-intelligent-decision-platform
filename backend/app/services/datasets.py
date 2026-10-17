from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.errors import NotFound, Unprocessable
from ..db.models import Dataset, Experiment, ModelRecord
from ..ml.errors import ArtifactError
from ..ml.ingest import load_csv_bytes, read_stored_csv
from ..ml.profiling import profile_dataframe
from ..ml.tracking import jsonable, new_id
from ..security.files import display_name, new_stored_name, resolve_inside, write_atomic
from .audit import record_audit
from .retention import compute_expiry, utcnow

logger = logging.getLogger(__name__)


def create_dataset(db: Session, settings: Settings, content: bytes, filename: str | None, *, synthetic: bool = False, actor: str = "system") -> Dataset:
    df = load_csv_bytes(content, max_bytes=settings.max_upload_bytes, max_rows=settings.max_rows, max_cols=settings.max_cols)
    profile = jsonable(profile_dataframe(df))
    now = utcnow()
    stored = new_stored_name("ds", "csv")
    path = settings.datasets_dir / stored
    write_atomic(path, content)
    ds = Dataset(
        id=new_id("ds"),
        name=display_name(filename),
        stored_filename=stored,
        sha256=hashlib.sha256(content).hexdigest(),
        n_rows=int(len(df)),
        n_cols=int(df.shape[1]),
        size_bytes=len(content),
        is_synthetic=synthetic,
        profile_json=profile,
        created_at=now,
        expires_at=compute_expiry(now, settings.retention_days),
    )
    try:
        db.add(ds)
        record_audit(db, actor, "dataset.create", "dataset", ds.id, {"rows": ds.n_rows, "cols": ds.n_cols, "synthetic": synthetic})
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return ds


def create_demo_dataset(db: Session, settings: Settings, actor: str = "system") -> Dataset:
    """Load the bundled synthetic sample (generating it on the fly if the file is absent)."""
    if settings.sample_csv.is_file():
        content = settings.sample_csv.read_bytes()
    else:
        from ..ml.ingest import to_safe_csv
        from ..ml.synthetic import generate_accounts

        content = to_safe_csv(generate_accounts()[0]).encode("utf-8")
    return create_dataset(db, settings, content, "nexus_synthetic_accounts.csv", synthetic=True, actor=actor)


def get_dataset(db: Session, dataset_id: str) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFound("Dataset not found.")
    return ds


def dataset_frame(settings: Settings, ds: Dataset) -> pd.DataFrame:
    try:
        path = resolve_inside(settings.datasets_dir, ds.stored_filename)
    except ValueError as exc:
        raise NotFound("Dataset file is unavailable.") from exc
    if not path.is_file():
        raise NotFound("Dataset file is no longer available (it may have been purged by the retention policy).")
    if hashlib.sha256(path.read_bytes()).hexdigest() != ds.sha256:
        raise ArtifactError("The stored dataset failed its integrity check.", code="dataset_corrupt")
    return read_stored_csv(path)


def dataset_preview(df: pd.DataFrame, rows: int) -> dict:
    head = df.head(rows)
    return {
        "columns": [str(c) for c in head.columns],
        "rows": [[jsonable(v) for v in r] for r in head.itertuples(index=False, name=None)],
        "total_rows": int(len(df)),
    }


def require_columns(ds: Dataset, columns: list[str] | None) -> None:
    if not columns:
        return
    known = {c["name"] for c in ds.profile_json["columns"]}
    unknown = [c for c in columns if c not in known]
    if unknown:
        raise Unprocessable(f"Unknown column(s): {', '.join(repr(c[:40]) for c in unknown[:5])}.", code="unknown_columns")


def delete_dataset(db: Session, settings: Settings, ds: Dataset, actor: str = "system") -> None:
    """Delete a dataset, its experiments, models and files."""
    artifacts = db.scalars(
        select(ModelRecord.artifact_filename).join(Experiment, ModelRecord.experiment_id == Experiment.id).where(Experiment.dataset_id == ds.id)
    ).all()
    stored = ds.stored_filename
    ds_id = ds.id
    db.delete(ds)
    record_audit(db, actor, "dataset.delete", "dataset", ds_id, {"models_removed": len(artifacts)})
    db.commit()
    for name in artifacts:
        _unlink(settings.models_dir, name)
    _unlink(settings.datasets_dir, stored)
    from .models import clear_bundle_cache

    clear_bundle_cache()


def purge_expired(db: Session, settings: Settings, actor: str = "retention-policy") -> int:
    now = utcnow()
    expired = db.scalars(select(Dataset).where(Dataset.expires_at.is_not(None), Dataset.expires_at < now)).all()
    for ds in expired:
        delete_dataset(db, settings, ds, actor)
    if expired:
        logger.info("retention purge completed", extra={"datasets_deleted": len(expired)})
    return len(expired)


def _unlink(base: Path, name: str) -> None:
    try:
        resolve_inside(base, name).unlink(missing_ok=True)
    except (ValueError, OSError):
        logger.warning("could not remove file", extra={"file": name})
