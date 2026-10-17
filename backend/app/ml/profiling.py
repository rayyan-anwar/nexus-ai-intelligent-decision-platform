"""Column-kind inference and dataset profiling."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import accel

_ID_TOKENS = {"id", "uuid", "guid", "key", "index", "idx"}


def _name_tokens(name: str) -> set[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))
    return {t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t}


def name_looks_like_id(name: str) -> bool:
    return bool(_name_tokens(name) & _ID_TOKENS)


def _numeric_share(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float(pd.to_numeric(values.astype(str), errors="coerce").notna().mean())


def _looks_like_datetime(values: pd.Series) -> bool:
    sample = values.astype(str).head(100)
    if sample.empty or sample.str.len().mean() < 8:
        return False
    if not sample.str.contains(r"[-/:]", regex=True).mean() > 0.9:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="ISO8601")
    return bool(parsed.notna().mean() >= 0.9)


def infer_kind(s: pd.Series) -> str:
    """One of: numeric, numeric_like, categorical, boolean, datetime, identifier, text, constant, empty."""
    n = len(s)
    values = s.dropna()
    nn = len(values)
    if nn == 0:
        return "empty"
    nunique = int(values.nunique())
    if pd.api.types.is_bool_dtype(s):
        return "boolean" if nunique > 1 else "constant"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if nunique <= 1:
        return "constant"
    if pd.api.types.is_numeric_dtype(s):
        if (
            pd.api.types.is_integer_dtype(s)
            and nunique == nn
            and nn >= 20
            and (name_looks_like_id(s.name) or values.is_monotonic_increasing)
        ):
            return "identifier"
        return "numeric"
    # object / string / category columns
    share = _numeric_share(values)
    if share >= 0.9:
        return "numeric_like"
    if _looks_like_datetime(values):
        return "datetime"
    avg_len = float(values.astype(str).str.len().mean())
    if nn >= 20 and nunique / nn >= 0.95:
        return "text" if avg_len > 40 else "identifier"
    if nunique <= 50 or nunique / nn <= 0.2:
        return "categorical"
    return "text" if avg_len > 40 else "categorical"


def invalid_numeric_entries(s: pd.Series) -> pd.Series:
    """Entries of a numeric-like text column that cannot be parsed as numbers."""
    values = s.dropna()
    coerced = pd.to_numeric(values.astype(str), errors="coerce")
    return values[coerced.isna()]


def to_numeric_clean(s: pd.Series) -> pd.Series:
    """Coerce to float; unparseable and infinite values become NaN."""
    out = pd.to_numeric(s, errors="coerce").astype(float)
    return out.mask(np.isinf(out))


def _numeric_stats(s: pd.Series) -> dict:
    x = to_numeric_clean(s).to_numpy()
    st = accel.column_stats(x)
    finite = x[np.isfinite(x)]
    if finite.size:
        q = np.percentile(finite, [25, 50, 75])
        quart = {"q25": float(q[0]), "median": float(q[1]), "q75": float(q[2])}
    else:
        quart = {"q25": None, "median": None, "q75": None}

    def clean(v):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)

    return {
        "min": clean(st["min"]),
        "max": clean(st["max"]),
        "mean": clean(st["mean"]),
        "std": clean(st["std"]),
        **quart,
    }


def histogram(s: pd.Series, bins: int = 20) -> dict:
    x = to_numeric_clean(s).dropna().to_numpy()
    if x.size == 0:
        return {"edges": [], "counts": []}
    counts, edges = np.histogram(x, bins=min(bins, max(1, int(np.sqrt(x.size)) + 1)))
    return {"edges": [float(e) for e in edges], "counts": [int(c) for c in counts]}


def profile_dataframe(df: pd.DataFrame, *, min_top_count: int = 3) -> dict:
    """Describe a dataset. Raw values are only included for low-cardinality categories seen >= ``min_top_count`` times."""
    n = len(df)
    columns = []
    kind_counts: dict[str, int] = {}
    for name in df.columns:
        s = df[name]
        kind = infer_kind(s)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        missing = int(s.isna().sum())
        col: dict = {
            "name": str(name),
            "dtype": str(s.dtype),
            "kind": kind,
            "missing": missing,
            "missing_pct": round(100.0 * missing / n, 2) if n else 0.0,
            "unique": int(s.nunique(dropna=True)),
        }
        if kind in {"numeric", "numeric_like"}:
            col["stats"] = _numeric_stats(s)
            col["histogram"] = histogram(s)
            if kind == "numeric_like":
                col["invalid_entries"] = int(len(invalid_numeric_entries(s)))
        elif kind in {"categorical", "boolean"}:
            vc = s.dropna().astype(str).value_counts()
            vc = vc[vc >= min_top_count].head(8)
            col["top_values"] = [{"value": str(k), "count": int(v)} for k, v in vc.items()]
        columns.append(col)
    return {
        "n_rows": int(n),
        "n_cols": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "kind_counts": kind_counts,
        "columns": columns,
    }
