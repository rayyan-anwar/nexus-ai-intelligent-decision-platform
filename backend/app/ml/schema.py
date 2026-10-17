"""Feature schema: what a model expects, and how new records are validated against it."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .errors import PredictionInputError
from .profiling import infer_kind, to_numeric_clean

MAX_CATEGORIES_STORED = 200


@dataclass
class FeatureSpec:
    name: str
    kind: str  # "numeric" | "categorical"
    categories: list[str] | None = None
    min: float | None = None
    max: float | None = None
    median: float | None = None
    mode: str | None = None
    missing_rate: float = 0.0


@dataclass
class FeatureSchema:
    features: list[FeatureSpec]
    target: str
    task: str
    classes: list[str] = field(default_factory=list)
    positive_label: str | None = None
    excluded: dict[str, str] = field(default_factory=dict)

    @property
    def feature_names(self) -> list[str]:
        return [f.name for f in self.features]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FeatureSchema:
        return cls(
            features=[FeatureSpec(**f) for f in d["features"]],
            target=d["target"],
            task=d["task"],
            classes=list(d.get("classes", [])),
            positive_label=d.get("positive_label"),
            excluded=dict(d.get("excluded", {})),
        )

    # ------------------------------------------------------------------ #
    def coerce(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Return a frame with exactly the model's feature columns plus human-readable issues."""
        issues: list[str] = []
        names = self.feature_names
        missing = [n for n in names if n not in df.columns]
        if len(missing) == len(names):
            raise PredictionInputError("None of the model's input columns were provided.", code="no_matching_columns")
        extra = [c for c in df.columns if c not in names]
        if extra:
            issues.append(f"{len(extra)} unrecognised column(s) were ignored.")
        out: dict[str, pd.Series] = {}
        for spec in self.features:
            if spec.name not in df.columns:
                issues.append(f"Column '{spec.name}' was not provided; training-time imputation is used.")
                fill = np.nan
                out[spec.name] = pd.Series([fill] * len(df), index=df.index, dtype=float if spec.kind == "numeric" else object)
                continue
            col = df[spec.name]
            if spec.kind == "numeric":
                clean = to_numeric_clean(col)
                bad = int((col.notna() & clean.isna()).sum())
                if bad:
                    issues.append(f"{bad} value(s) in '{spec.name}' are not valid numbers and were treated as missing.")
                if spec.min is not None and spec.max is not None:
                    outside = int(((clean < spec.min) | (clean > spec.max)).sum())
                    if outside:
                        issues.append(
                            f"{outside} value(s) in '{spec.name}' lie outside the training range "
                            f"[{spec.min:.4g}, {spec.max:.4g}]; predictions may be unreliable."
                        )
                out[spec.name] = clean
            else:
                as_text = col.map(lambda v: str(v) if pd.notna(v) else np.nan).astype(object)
                if spec.categories is not None:
                    unseen = sorted({str(v) for v in as_text.dropna().unique()} - set(spec.categories))
                    if unseen:
                        shown = ", ".join(repr(u[:30]) for u in unseen[:5])
                        issues.append(f"Unseen categories in '{spec.name}' ({shown}); the model has no experience with them.")
                out[spec.name] = as_text
        return pd.DataFrame(out, index=df.index), issues


def plan_features(df: pd.DataFrame, target: str, exclude: list[str] | None = None) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Decide which columns become model features. Returns ``([(name, kind)], {excluded: reason})``."""
    exclude = set(exclude or [])
    plan: list[tuple[str, str]] = []
    excluded: dict[str, str] = {}
    for name in df.columns:
        if name == target:
            continue
        if name in exclude:
            excluded[name] = "excluded by user"
            continue
        kind = infer_kind(df[name])
        if kind in {"numeric", "numeric_like"}:
            plan.append((name, "numeric"))
        elif kind in {"categorical", "boolean"}:
            plan.append((name, "categorical"))
        else:
            excluded[name] = f"{kind} column is not used as a feature"
    return plan, excluded


def fit_schema(
    plan: list[tuple[str, str]],
    X_train: pd.DataFrame,
    *,
    target: str,
    task: str,
    classes: list[str],
    positive_label: str | None,
    excluded: dict[str, str],
) -> FeatureSchema:
    """Record feature statistics from the TRAINING rows only."""
    specs: list[FeatureSpec] = []
    for name, kind in plan:
        col = X_train[name]
        missing_rate = float(col.isna().mean())
        if kind == "numeric":
            clean = to_numeric_clean(col).dropna()
            specs.append(
                FeatureSpec(
                    name=name,
                    kind=kind,
                    min=float(clean.min()) if len(clean) else None,
                    max=float(clean.max()) if len(clean) else None,
                    median=float(clean.median()) if len(clean) else None,
                    missing_rate=missing_rate,
                )
            )
        else:
            text = col.dropna().astype(str)
            vc = text.value_counts()
            cats = sorted(vc.index.tolist())
            specs.append(
                FeatureSpec(
                    name=name,
                    kind=kind,
                    categories=cats if len(cats) <= MAX_CATEGORIES_STORED else None,
                    mode=str(vc.index[0]) if len(vc) else None,
                    missing_rate=missing_rate,
                )
            )
    return FeatureSchema(
        features=specs,
        target=target,
        task=task,
        classes=classes,
        positive_label=positive_label,
        excluded=excluded,
    )
