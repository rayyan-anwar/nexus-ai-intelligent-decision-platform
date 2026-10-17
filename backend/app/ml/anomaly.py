"""Unsupervised anomaly detection with Isolation Forest."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .errors import DataValidationError
from .profiling import infer_kind, to_numeric_clean

SENSITIVITY = {"low": 0.01, "medium": 0.03, "high": 0.08}
WARNING = (
    "An anomaly score only says a record is unusual compared with the rest of this dataset. "
    "It does not mean fraud, an error or wrongdoing; review flagged records with domain knowledge."
)


def resolve_contamination(sensitivity: str | float) -> float:
    if isinstance(sensitivity, str):
        if sensitivity not in SENSITIVITY:
            raise DataValidationError(f"sensitivity must be one of {sorted(SENSITIVITY)} or a number between 0.001 and 0.3.")
        return SENSITIVITY[sensitivity]
    value = float(sensitivity)
    if not 0.001 <= value <= 0.3:
        raise DataValidationError("A numeric sensitivity (expected share flagged) must be between 0.001 and 0.3.")
    return value


def _select_columns(df: pd.DataFrame, columns: list[str] | None) -> tuple[list[str], list[str], str | None]:
    numeric, categorical = [], []
    row_id_col = None
    for name in df.columns:
        if columns is not None and name not in columns:
            continue
        kind = infer_kind(df[name])
        if kind == "identifier" and row_id_col is None:
            row_id_col = str(name)
        if kind in {"numeric", "numeric_like"}:
            numeric.append(str(name))
        elif kind in {"categorical", "boolean"}:
            categorical.append(str(name))
    return numeric, categorical, row_id_col


def detect_anomalies(
    df: pd.DataFrame,
    *,
    sensitivity: str | float = "medium",
    seed: int = 42,
    columns: list[str] | None = None,
    n_estimators: int = 200,
    max_rows: int = 200,
) -> dict:
    if len(df) < 20:
        raise DataValidationError("At least 20 rows are needed for anomaly detection.")
    contamination = resolve_contamination(sensitivity)
    numeric, categorical, row_id_col = _select_columns(df, columns)
    if not numeric and not categorical:
        raise DataValidationError("No usable numeric or categorical columns were found.")

    X = pd.DataFrame(index=df.index)
    for c in numeric:
        X[c] = to_numeric_clean(df[c])
    for c in categorical:
        X[c] = df[c].map(lambda v: str(v) if pd.notna(v) else np.nan).astype(object)

    transformers = []
    if numeric:
        transformers.append(("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), numeric))
    if categorical:
        transformers.append((
            "cat",
            Pipeline([
                ("imp", SimpleImputer(strategy="constant", fill_value="__missing__")),
                ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=0.01, sparse_output=False)),
            ]),
            categorical,
        ))
    pre = ColumnTransformer(transformers, remainder="drop")
    Z = pre.fit_transform(X)
    forest = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=seed, n_jobs=1)
    labels = forest.fit_predict(Z)
    raw = -forest.score_samples(Z)  # higher = more anomalous
    span = raw.max() - raw.min()
    scores = (raw - raw.min()) / span if span > 0 else np.zeros_like(raw)
    threshold_raw = -forest.offset_
    threshold = float((threshold_raw - raw.min()) / span) if span > 0 else 0.0
    flagged = np.where(labels == -1)[0]

    # Robust per-feature deviations to explain *why* a row is unusual.
    medians, scales = {}, {}
    for c in numeric:
        col = X[c].dropna()
        med = float(col.median()) if len(col) else 0.0
        mad = float((col - med).abs().median()) * 1.4826 if len(col) else 0.0
        std = float(col.std()) if len(col) > 1 else 0.0
        medians[c] = med
        scales[c] = mad if mad > 0 else (std if std > 0 else 1.0)
    freq = {c: X[c].value_counts(normalize=True) for c in categorical}

    order = flagged[np.argsort(-scores[flagged])][:max_rows]
    rows = []
    for i in order:
        reasons = []
        for c in numeric:
            v = X[c].iloc[i]
            if pd.notna(v):
                z = abs(v - medians[c]) / scales[c]
                if z >= 3.5:
                    reasons.append({"feature": c, "robust_z": round(float(z), 2), "kind": "numeric_outlier"})
        for c in categorical:
            v = X[c].iloc[i]
            if pd.notna(v) and freq[c].get(v, 0) < 0.01:
                reasons.append({"feature": c, "kind": "rare_category"})
        reasons.sort(key=lambda r: -r.get("robust_z", 0))
        rows.append({
            "row_index": int(df.index[i]) if isinstance(df.index[i], (int, np.integer)) else int(i),
            "row_id": str(df[row_id_col].iloc[i]) if row_id_col else None,
            "score": round(float(scores[i]), 4),
            "reasons": reasons[:3],
        })

    hist_counts, hist_edges = np.histogram(scores, bins=20, range=(0, 1))
    return {
        "n_rows": int(len(df)),
        "n_flagged": int(len(flagged)),
        "contamination": contamination,
        "threshold": round(threshold, 4),
        "seed": seed,
        "features_used": numeric + categorical,
        "row_id_column": row_id_col,
        "score_histogram": {"edges": [round(float(e), 3) for e in hist_edges], "counts": [int(c) for c in hist_counts]},
        "flagged": rows,
        "scores": [round(float(s), 5) for s in scores],
        "flagged_indices": [int(i) for i in flagged],
        "warning": WARNING,
    }


def anomaly_table(df: pd.DataFrame, result: dict) -> pd.DataFrame:
    """Flagged rows with their score and top reasons, ready for export."""
    idx = result["flagged_indices"]
    scores = np.asarray(result["scores"])
    table = df.iloc[idx].copy()
    table.insert(0, "anomaly_score", scores[idx])
    reason_map = {r["row_index"]: "; ".join(x["feature"] for x in r["reasons"]) for r in result["flagged"]}
    table.insert(1, "main_features", [reason_map.get(int(df.index[i]), "") for i in idx])
    return table.sort_values("anomaly_score", ascending=False).reset_index(drop=True)
