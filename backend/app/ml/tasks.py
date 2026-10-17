"""Target-column suggestion and task-type inference."""

from __future__ import annotations

import re

import pandas as pd

from .errors import UnsupportedTaskError
from .profiling import infer_kind, to_numeric_clean

MAX_CLASSES = 20
MAX_INTEGER_CLASSES = 10
TASKS = ("binary", "multiclass", "regression")
_NAME_HINTS = {
    "target", "label", "class", "churn", "churned", "outcome", "default", "fraud", "price",
    "amount", "spend", "revenue", "score", "risk", "status", "tier", "y", "survived", "cost",
}


def infer_task(target: pd.Series, override: str | None = None) -> tuple[str, list[str]]:
    """Return ``(task, notes)`` or raise :class:`UnsupportedTaskError` with a clear reason."""
    notes: list[str] = []
    if override is not None and override not in TASKS:
        raise UnsupportedTaskError(f"Unknown task '{override}'. Supported: {', '.join(TASKS)}.")
    kind = infer_kind(target)
    if kind in {"empty", "constant", "datetime", "identifier", "text"}:
        raise UnsupportedTaskError(f"The target column looks like a {kind} column and cannot be predicted.")
    values = target.dropna()
    nunique = int(values.nunique())
    if nunique < 2:
        raise UnsupportedTaskError("The target column has fewer than two distinct values.")
    numeric_kind = kind in {"numeric", "numeric_like"}
    if numeric_kind:
        clean = to_numeric_clean(target).dropna()
        nunique = int(clean.nunique())
        integer_valued = bool((clean == clean.round()).all())
    else:
        integer_valued = False

    if override == "regression":
        if not numeric_kind:
            raise UnsupportedTaskError("Regression needs a numeric target column.")
        return "regression", notes
    if override in {"binary", "multiclass"}:
        if nunique > MAX_CLASSES:
            raise UnsupportedTaskError(f"The target has {nunique} distinct values; at most {MAX_CLASSES} classes are supported.")
        if override == "binary" and nunique != 2:
            raise UnsupportedTaskError(f"Binary classification needs exactly 2 classes but the target has {nunique}.")
        if override == "multiclass" and nunique < 3:
            raise UnsupportedTaskError("Multiclass classification needs at least 3 classes.")
        return override, notes

    if kind == "boolean" or nunique == 2:
        return "binary", notes
    if numeric_kind:
        if integer_valued and nunique <= MAX_INTEGER_CLASSES:
            notes.append(
                f"Integer target with {nunique} distinct values was treated as classes. "
                "If it is a count, set the task to regression."
            )
            return "multiclass", notes
        return "regression", notes
    if nunique <= MAX_CLASSES:
        return "multiclass", notes
    raise UnsupportedTaskError(
        f"The target has {nunique} distinct text values; at most {MAX_CLASSES} classes are supported."
    )


def suggest_targets(df: pd.DataFrame, max_suggestions: int = 5) -> list[dict]:
    """Rank plausible target columns. The caller must still ask the user to confirm."""
    n = len(df)
    suggestions: list[dict] = []
    for pos, name in enumerate(df.columns):
        s = df[name]
        if n == 0 or s.notna().mean() < 0.5:
            continue
        try:
            task, _ = infer_task(s)
        except UnsupportedTaskError:
            continue
        score = 0.1
        reasons: list[str] = []
        tokens = {t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t}
        if tokens & _NAME_HINTS:
            score += 0.5
            reasons.append("column name suggests an outcome")
        if pos == len(df.columns) - 1:
            score += 0.15
            reasons.append("last column")
        if task == "binary":
            score += 0.15
            reasons.append("two distinct values")
        elif task == "multiclass":
            score += 0.05
        score -= 0.3 * float(s.isna().mean())
        suggestions.append({"column": str(name), "task": task, "score": round(score, 3), "reasons": reasons})
    suggestions.sort(key=lambda d: d["score"], reverse=True)
    return suggestions[:max_suggestions]
