"""Experiment tracking helpers: fingerprints, ids, versions, JSON safety and artifact IO."""

from __future__ import annotations

import hashlib
import math
import platform
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn

from .errors import ArtifactError


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dataset_fingerprint(df: pd.DataFrame) -> str:
    """Content hash of a dataset (column names, order and values). Stable across runs and machines."""
    h = hashlib.sha256()
    h.update("|".join(f"{c}" for c in df.columns).encode("utf-8"))
    row_hashes = pd.util.hash_pandas_object(df.astype(str), index=False).to_numpy()
    h.update(row_hashes.tobytes())
    return h.hexdigest()


def software_versions() -> dict[str, str]:
    from .. import __version__

    return {
        "nexus_app": __version__,
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }


def jsonable(obj: Any) -> Any:
    """Recursively convert numpy/pandas values to JSON-safe Python values (NaN/inf -> None)."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_bundle(bundle, directory: str | Path, model_id: str) -> tuple[Path, str]:
    """Persist a model bundle under a generated filename and return ``(path, sha256)``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{model_id}.joblib"
    joblib.dump(bundle, path, compress=3)
    return path, file_sha256(path)


def load_bundle(path: str | Path, expected_sha256: str):
    """Load a bundle after verifying its checksum.

    joblib/pickle can execute code on load, so only artifacts written by this
    application (and whose recorded checksum still matches) are ever loaded.
    """
    path = Path(path)
    if not path.is_file():
        raise ArtifactError("The model artifact is missing.", code="artifact_missing")
    if not expected_sha256 or file_sha256(path) != expected_sha256:
        raise ArtifactError("The model artifact failed its integrity check.", code="artifact_corrupt")
    try:
        return joblib.load(path)
    except Exception as exc:  # noqa: BLE001 - surface as a safe domain error
        raise ArtifactError("The model artifact could not be loaded.", code="artifact_unreadable") from exc
