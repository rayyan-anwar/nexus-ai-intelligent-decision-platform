"""Model-agnostic explanations.

* Global: permutation importance on the validation split (computed at training time).
* Local: Monte-Carlo Shapley values over the ORIGINAL input features (interventional,
  background-sample based). Contributions are additive:
  ``base_value + sum(contributions) == model_output`` (exact per sampled permutation).

Explanations describe the model's behaviour. They do NOT establish causation.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from .errors import PredictionInputError
from .pipeline import CLASSIFICATION, ModelBundle
from .tracking import jsonable

LOCAL_CAVEATS = [
    "Contributions explain this model's output for this record, not real-world cause and effect.",
    "Values are estimated by sampling permutations against a small background set and carry Monte-Carlo error (see std_error).",
    "Correlated features share credit and the background mixes feature values, which may create unrealistic combinations.",
    "Explanations can change if the model is retrained or the background sample differs.",
]


def output_function(bundle: ModelBundle, target_class: str | None) -> tuple[Callable[[pd.DataFrame], np.ndarray], str]:
    task = bundle.metadata["task"]
    if task in CLASSIFICATION:
        classes = [str(c) for c in bundle.pipeline.classes_]
        idx = classes.index(target_class)
        return (lambda X: bundle.pipeline.predict_proba(X)[:, idx]), f"predicted probability of '{target_class}'"
    return (lambda X: bundle.pipeline.predict(X)), f"predicted {bundle.metadata['target']}"


def global_importance(bundle: ModelBundle, summary: dict | None = None) -> dict[str, Any]:
    """Global importance recorded at training time. ``summary`` is the stored experiment summary."""
    if summary is None:
        raise PredictionInputError("Experiment summary is required for global importance.")
    return {
        "method": "permutation importance on the validation split",
        "metric": summary["primary_metric"],
        "importance": summary["importance"],
        "warnings": summary["explanation_warnings"],
        "interpretation": (
            "Importance is the average drop in the model's primary validation metric when a feature's values are shuffled. "
            "Larger means the model relies on the feature more. Values near zero (or negative) mean the model barely uses it. "
            "This is not a causal effect."
        ),
    }


def explain_instance(
    bundle: ModelBundle,
    record: dict,
    *,
    target_class: str | None = None,
    n_permutations: int = 30,
    background_size: int = 20,
    seed: int = 0,
) -> dict[str, Any]:
    if not isinstance(record, dict) or not record:
        raise PredictionInputError("Provide one record as an object of column/value pairs.", code="bad_records")
    if not 1 <= n_permutations <= 200:
        raise PredictionInputError("n_permutations must be between 1 and 200.")
    X, issues = bundle.schema.coerce(pd.DataFrame([record]))
    x_row = X.iloc[0]
    task = bundle.metadata["task"]
    if task in CLASSIFICATION:
        classes = [str(c) for c in bundle.pipeline.classes_]
        if target_class is None:
            target_class = classes[int(bundle.pipeline.predict_proba(X)[0].argmax())]
        elif target_class not in classes:
            raise PredictionInputError(f"target_class must be one of {classes}.")
    fn, description = output_function(bundle, target_class)

    bg_all = bundle.background
    if len(bg_all) == 0:
        raise PredictionInputError("This model has no background sample; local explanations are unavailable.", code="no_background")
    rng = np.random.default_rng(seed)
    take = rng.choice(len(bg_all), size=min(background_size, len(bg_all)), replace=False)
    bg = bg_all.iloc[take].reset_index(drop=True)
    features = list(X.columns)
    p, B = len(features), len(bg)

    total = np.zeros(p)
    total_sq = np.zeros(p)
    for _ in range(n_permutations):
        order = rng.permutation(p)
        cur = bg.copy()
        frames = [cur.copy()]
        for j in order:
            cur[features[j]] = x_row[features[j]]
            frames.append(cur.copy())
        vals = fn(pd.concat(frames, ignore_index=True)).reshape(p + 1, B)
        marginal = (vals[1:] - vals[:-1]).mean(axis=1)  # one entry per position in `order`
        contrib = np.zeros(p)
        contrib[order] = marginal
        total += contrib
        total_sq += contrib**2

    mean = total / n_permutations
    var = np.maximum(total_sq / n_permutations - mean**2, 0.0)
    stderr = np.sqrt(var / n_permutations)
    base_value = float(fn(bg).mean())
    output = float(fn(X)[0])

    items = []
    for j in np.argsort(-np.abs(mean)):
        v = x_row[features[j]]
        items.append({
            "feature": features[j],
            "value": None if pd.isna(v) else (float(v) if isinstance(v, (int, float, np.number)) else str(v)),
            "contribution": float(mean[j]),
            "std_error": float(stderr[j]),
            "direction": "increases" if mean[j] > 0 else "decreases" if mean[j] < 0 else "neutral",
        })
    return jsonable({
        "output": description,
        "target_class": target_class,
        "base_value": base_value,
        "model_output": output,
        "sum_of_contributions": float(mean.sum()),
        "contributions": items,
        "method": "Monte-Carlo Shapley (interventional, original features)",
        "n_permutations": n_permutations,
        "background_rows": B,
        "issues": issues,
        "caveats": LOCAL_CAVEATS,
        "interpretation": (
            f"Starting from the average {description} over the background sample ({base_value:.3f}), "
            f"each feature's contribution moves the estimate toward this record's value ({output:.3f}). "
            "Positive contributions push it up, negative ones push it down."
        ),
    })
