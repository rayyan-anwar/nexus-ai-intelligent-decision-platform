"""Data-quality report: missing values, duplicates, invalid types, unexpected categories."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import accel
from .profiling import infer_kind, invalid_numeric_entries, to_numeric_clean
from .schema import FeatureSchema


def _issue(severity: str, code: str, message: str, column: str | None = None, count: int | None = None) -> dict:
    return {"severity": severity, "code": code, "column": column, "message": message, "count": count}


def quality_report(df: pd.DataFrame, schema: FeatureSchema | None = None) -> dict:
    n = len(df)
    issues: list[dict] = []
    columns: list[dict] = []
    total_missing = int(df.isna().sum().sum())

    for name in df.columns:
        s = df[name]
        kind = infer_kind(s)
        missing = int(s.isna().sum())
        entry: dict = {"name": str(name), "kind": kind, "missing": missing, "missing_pct": round(100 * missing / n, 2) if n else 0.0}
        if missing == n:
            issues.append(_issue("error", "empty_column", f"Column '{name}' is entirely empty.", str(name), missing))
        elif missing:
            pct = 100 * missing / n
            sev = "warning" if pct >= 20 else "info"
            issues.append(_issue(sev, "missing_values", f"Column '{name}' has {missing} missing value(s) ({pct:.1f}%).", str(name), missing))

        if kind == "numeric_like":
            bad = invalid_numeric_entries(s)
            examples = [str(v)[:30] for v in bad.unique()[:3]]
            entry["invalid_entries"] = int(len(bad))
            issues.append(
                _issue(
                    "warning", "invalid_type",
                    f"Column '{name}' is mostly numeric but {len(bad)} entr{'y' if len(bad) == 1 else 'ies'} "
                    f"cannot be parsed (e.g. {', '.join(repr(e) for e in examples)}). They are treated as missing for modelling.",
                    str(name), int(len(bad)),
                )
            )
        if kind in {"numeric", "numeric_like"}:
            x = to_numeric_clean(s).to_numpy()
            raw = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
            st = accel.column_stats(raw)
            if st["inf"]:
                issues.append(_issue("warning", "infinite_values", f"Column '{name}' contains {st['inf']} infinite value(s).", str(name), st["inf"]))
            finite = x[np.isfinite(x)]
            if finite.size >= 20:
                q1, q3 = np.percentile(finite, [25, 75])
                iqr = q3 - q1
                if iqr > 0:
                    outliers = int(((finite < q1 - 3 * iqr) | (finite > q3 + 3 * iqr)).sum())
                    entry["extreme_outliers"] = outliers
                    if outliers:
                        issues.append(_issue("info", "extreme_outliers", f"Column '{name}' has {outliers} extreme outlier(s) (beyond 3 x IQR).", str(name), outliers))
        if kind == "constant":
            issues.append(_issue("info", "constant_column", f"Column '{name}' has a single value and carries no information.", str(name)))
        if kind == "identifier":
            issues.append(_issue("info", "identifier_column", f"Column '{name}' looks like an identifier and is excluded from modelling.", str(name)))
        if kind == "categorical" and s.nunique(dropna=True) > 50:
            issues.append(_issue("info", "high_cardinality", f"Column '{name}' has {s.nunique()} distinct categories; rare ones are grouped when modelling.", str(name)))
        columns.append(entry)

    dup = int(df.duplicated().sum())
    if dup:
        first = [int(i) for i in df.index[df.duplicated(keep="first")][:10]]
        issues.append(_issue("warning", "duplicate_rows", f"{dup} exact duplicate row(s) found (first at row indices {first}).", None, dup))

    unexpected: list[dict] = []
    if schema is not None:
        for spec in schema.features:
            if spec.name not in df.columns:
                issues.append(_issue("error", "missing_expected_column", f"Expected column '{spec.name}' is absent.", spec.name))
                continue
            col = df[spec.name]
            if spec.kind == "categorical" and spec.categories is not None:
                seen = col.dropna().astype(str)
                unseen = seen[~seen.isin(spec.categories)]
                if len(unseen):
                    top = unseen.value_counts().head(5)
                    unexpected.append({"column": spec.name, "values": {str(k)[:30]: int(v) for k, v in top.items()}, "rows": int(len(unseen))})
                    issues.append(_issue("warning", "unexpected_category", f"Column '{spec.name}' has {len(unseen)} row(s) with categories not seen in training.", spec.name, int(len(unseen))))
            if spec.kind == "numeric" and spec.min is not None and spec.max is not None:
                clean = to_numeric_clean(col)
                outside = int(((clean < spec.min) | (clean > spec.max)).sum())
                if outside:
                    issues.append(_issue("info", "outside_training_range", f"Column '{spec.name}' has {outside} value(s) outside the training range.", spec.name, outside))

    counts = {"error": 0, "warning": 0, "info": 0}
    for i in issues:
        counts[i["severity"]] += 1
    cells = n * max(df.shape[1], 1)
    return {
        "n_rows": int(n),
        "n_cols": int(df.shape[1]),
        "missing_cells": total_missing,
        "missing_cells_pct": round(100 * total_missing / cells, 2) if cells else 0.0,
        "duplicate_rows": dup,
        "severity_counts": counts,
        "unexpected_categories": unexpected,
        "columns": columns,
        "issues": sorted(issues, key=lambda i: {"error": 0, "warning": 1, "info": 2}[i["severity"]]),
    }
