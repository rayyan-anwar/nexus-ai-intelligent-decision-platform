"""Optional native acceleration with a pure-Python/NumPy fallback.

The C++ library lives in ``services/cpp-accelerator``. It exposes a plain C ABI
that is loaded through :mod:`ctypes`, so there is no build-time dependency on
pybind11 and the application never *requires* the native code.

Both code paths implement identical semantics and are covered by equivalence
tests (``backend/tests/test_accel.py``).
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_LIB: ctypes.CDLL | None = None
_LOAD_ATTEMPTED = False


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.getenv("NEXUS_ACCEL_LIB")
    if env:
        paths.append(Path(env))
    root = Path(__file__).resolve().parents[3]
    for name in ("libnexus_accel.so", "libnexus_accel.dylib", "nexus_accel.dll"):
        paths.append(root / "services" / "cpp-accelerator" / "build" / name)
    return paths


def _load() -> ctypes.CDLL | None:
    global _LIB, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _LIB
    _LOAD_ATTEMPTED = True
    if os.getenv("NEXUS_DISABLE_ACCEL", "").lower() in {"1", "true", "yes"}:
        return None
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            lib = ctypes.CDLL(str(path))
            lib.nexus_column_stats.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int64,
                ctypes.POINTER(ctypes.c_int64),
                ctypes.POINTER(ctypes.c_double),
            ]
            lib.nexus_column_stats.restype = ctypes.c_int
            lib.nexus_bin_counts.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int64,
                ctypes.c_void_p,
                ctypes.c_int64,
                ctypes.POINTER(ctypes.c_int64),
            ]
            lib.nexus_bin_counts.restype = ctypes.c_int
            _LIB = lib
            logger.info("native accelerator loaded", extra={"path": str(path)})
            return _LIB
        except OSError:  # pragma: no cover - platform dependent
            logger.warning("native accelerator present but could not be loaded", extra={"path": str(path)})
    return None


def native_available() -> bool:
    return _load() is not None


def _as_f64(values) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(values, dtype=np.float64).ravel())


# --------------------------------------------------------------------------- #
# column_stats: single-pass validity counts + moments
# --------------------------------------------------------------------------- #
def _py_column_stats(x: np.ndarray) -> dict:
    nan_mask = np.isnan(x)
    inf_mask = np.isinf(x)
    finite = x[~(nan_mask | inf_mask)]
    n_valid = int(finite.size)
    if n_valid == 0:
        mn = mx = mean = float("nan")
        m2 = 0.0
    else:
        mn = float(finite.min())
        mx = float(finite.max())
        mean = float(finite.mean())
        m2 = float(np.square(finite - mean).sum())
    return _finish_stats(n_valid, int(nan_mask.sum()), int(inf_mask.sum()), mn, mx, mean, m2)


def _finish_stats(n_valid, n_nan, n_inf, mn, mx, mean, m2) -> dict:
    std = float(np.sqrt(m2 / (n_valid - 1))) if n_valid > 1 else float("nan")
    return {
        "valid": n_valid,
        "nan": n_nan,
        "inf": n_inf,
        "min": mn,
        "max": mx,
        "mean": mean,
        "std": std,
    }


def column_stats(values, *, force_python: bool = False) -> dict:
    """Counts of finite/NaN/inf values plus min, max, mean and sample std of the finite values."""
    x = _as_f64(values)
    lib = None if force_python else _load()
    if lib is None or x.size == 0:
        return _py_column_stats(x)
    counts = (ctypes.c_int64 * 3)()
    vals = (ctypes.c_double * 4)()
    rc = lib.nexus_column_stats(x.ctypes.data, x.size, counts, vals)
    if rc != 0:  # pragma: no cover - defensive
        return _py_column_stats(x)
    return _finish_stats(int(counts[0]), int(counts[1]), int(counts[2]), vals[0], vals[1], vals[2], vals[3])


# --------------------------------------------------------------------------- #
# bin_counts: histogram with explicit edges (bin = number of edges <= x)
# --------------------------------------------------------------------------- #
def _py_bin_counts(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    x = x[~np.isnan(x)]
    idx = np.searchsorted(edges, x, side="right")
    return np.bincount(idx, minlength=edges.size + 1).astype(np.int64)


def bin_counts(values, edges, *, force_python: bool = False) -> np.ndarray:
    """Counts per bin for ascending ``edges``; returns ``len(edges) + 1`` counts. NaNs are skipped."""
    x = _as_f64(values)
    e = _as_f64(edges)
    if e.size > 1 and np.any(np.diff(e) < 0):
        raise ValueError("edges must be sorted in ascending order")
    lib = None if force_python else _load()
    if lib is None or x.size == 0:
        return _py_bin_counts(x, e)
    out = (ctypes.c_int64 * (e.size + 1))()
    rc = lib.nexus_bin_counts(x.ctypes.data, x.size, e.ctypes.data, e.size, out)
    if rc != 0:  # pragma: no cover - defensive
        return _py_bin_counts(x, e)
    return np.frombuffer(out, dtype=np.int64).copy()
