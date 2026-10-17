"""Training, model selection, evaluation and inference for tabular data.

Design rules enforced here
--------------------------
* Preprocessing is part of the scikit-learn ``Pipeline`` and is fitted on the TRAINING split only.
* Models are compared on the VALIDATION split. The TEST split is evaluated exactly once, for the
  already-selected model (plus the baseline for context), and never influences selection.
* The same fitted pipeline object is used for inference, so training and serving preprocessing are identical.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    precision_recall_fscore_support,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .. import __version__
from .errors import DataValidationError, PredictionInputError, UnsupportedTaskError
from .profiling import to_numeric_clean
from .schema import FeatureSchema, fit_schema, plan_features
from .tasks import infer_task
from .tracking import jsonable, software_versions

CLASSIFICATION = {"binary", "multiclass"}
MIN_ROWS = 50
MIN_PER_CLASS = 5
LOW_CONFIDENCE = 0.6
INTERVAL_LEVEL = 0.9
Progress = Callable[[str, float], None]


@dataclass
class TrainConfig:
    target: str
    task: str | None = None
    seed: int = 42
    test_size: float = 0.2
    val_size: float = 0.2
    model_names: list[str] | None = None
    exclude_columns: list[str] = field(default_factory=list)
    positive_label: str | None = None
    n_jobs: int = 1
    background_size: int = 50
    importance_repeats: int = 5

    def validate(self) -> None:
        if not 0.05 <= self.test_size <= 0.5 or not 0.05 <= self.val_size <= 0.5:
            raise DataValidationError("test_size and val_size must each be between 0.05 and 0.5.")
        if self.test_size + self.val_size > 0.8:
            raise DataValidationError("test_size + val_size must not exceed 0.8.")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise DataValidationError("seed must be a non-negative integer.")


@dataclass
class ModelBundle:
    pipeline: Pipeline
    schema: FeatureSchema
    metadata: dict[str, Any]
    background: pd.DataFrame


@dataclass
class TrainingResult:
    bundle: ModelBundle
    summary: dict[str, Any]


# --------------------------------------------------------------------------- #
# Model zoo
# --------------------------------------------------------------------------- #
def model_zoo(task: str, seed: int, n_jobs: int = 1) -> dict[str, Callable[[], Any]]:
    if task in CLASSIFICATION:
        return {
            "logistic_regression": lambda: LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed),
            "random_forest": lambda: RandomForestClassifier(
                n_estimators=200, min_samples_leaf=2, class_weight="balanced", random_state=seed, n_jobs=n_jobs
            ),
            "gradient_boosting": lambda: GradientBoostingClassifier(n_estimators=150, max_depth=3, random_state=seed),
        }
    return {
        "linear_regression": lambda: LinearRegression(),
        "random_forest": lambda: RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=n_jobs),
        "gradient_boosting": lambda: GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=seed),
    }


def baseline_estimator(task: str):
    return DummyClassifier(strategy="prior") if task in CLASSIFICATION else DummyRegressor(strategy="mean")


def build_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    parts = []
    if numeric:
        parts.append(("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric))
    if categorical:
        parts.append((
            "cat",
            Pipeline([
                ("impute", SimpleImputer(strategy="constant", fill_value="__missing__")),
                ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=0.01, max_categories=30, sparse_output=False)),
            ]),
            categorical,
        ))
    return ColumnTransformer(parts, remainder="drop")


def make_pipeline(schema_plan: list[tuple[str, str]], estimator) -> Pipeline:
    numeric = [n for n, k in schema_plan if k == "numeric"]
    categorical = [n for n, k in schema_plan if k == "categorical"]
    return Pipeline([("prep", build_preprocessor(numeric, categorical)), ("model", estimator)])


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _safe(fn, *args, **kwargs):
    try:
        v = fn(*args, **kwargs)
        v = float(v)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def classification_metrics(y_true, y_pred, proba, classes: list[str], pos_label: str | None) -> dict[str, Any]:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    binary = len(classes) == 2
    avg = "binary" if binary else "macro"
    kwargs = {"pos_label": pos_label} if binary else {}
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average=avg, zero_division=0, **kwargs)
    pc, rc, fc, sc = precision_recall_fscore_support(y_true, y_pred, labels=classes, zero_division=0)
    m: dict[str, Any] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(p),
        "recall": float(r),
        "f1": float(f),
        "f1_macro": float(precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)[2]),
        "log_loss": _safe(log_loss, y_true, proba, labels=classes),
        "confusion_matrix": {"labels": classes, "matrix": confusion_matrix(y_true, y_pred, labels=classes).tolist()},
        "per_class": [
            {"label": c, "precision": float(pc[i]), "recall": float(rc[i]), "f1": float(fc[i]), "support": int(sc[i])}
            for i, c in enumerate(classes)
        ],
    }
    if binary:
        pos_idx = classes.index(pos_label)
        y_bin = (y_true == pos_label).astype(int)
        m["roc_auc"] = _safe(roc_auc_score, y_bin, proba[:, pos_idx])
        m["pr_auc"] = _safe(average_precision_score, y_bin, proba[:, pos_idx])
        m["brier"] = _safe(brier_score_loss, y_bin, proba[:, pos_idx])
    else:
        m["roc_auc"] = _safe(roc_auc_score, y_true, proba, multi_class="ovr", average="macro", labels=classes)
        m["pr_auc"] = None
    return m


def regression_metrics(y_true, y_pred, *, include_residuals: bool = True, seed: int = 0) -> dict[str, Any]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    res = y_true - y_pred
    m: dict[str, Any] = {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": _safe(r2_score, y_true, y_pred),
        "median_ae": float(median_absolute_error(y_true, y_pred)),
    }
    if include_residuals:
        q = np.percentile(res, [5, 25, 50, 75, 95])
        rng = np.random.default_rng(seed)
        take = rng.choice(len(res), size=min(300, len(res)), replace=False)
        m["residuals"] = {
            "mean": float(res.mean()),
            "std": float(res.std(ddof=1)) if len(res) > 1 else 0.0,
            "percentiles": {"p5": float(q[0]), "p25": float(q[1]), "p50": float(q[2]), "p75": float(q[3]), "p95": float(q[4])},
            "sample": [{"predicted": float(y_pred[i]), "residual": float(res[i])} for i in take],
        }
    return m


def primary_metric_spec(task: str, y_train: pd.Series) -> dict[str, str]:
    if task == "regression":
        return {"name": "rmse", "direction": "lower"}
    if task == "multiclass":
        return {"name": "f1_macro", "direction": "higher"}
    minority = float(y_train.value_counts(normalize=True).min())
    return {"name": "pr_auc" if minority < 0.2 else "roc_auc", "direction": "higher"}


def _oriented(value: float | None, spec: dict[str, str]) -> float:
    if value is None:
        return -math.inf
    return -value if spec["direction"] == "lower" else value


def evaluate(pipeline: Pipeline, X, y, task: str, classes: list[str], pos_label: str | None, seed: int = 0) -> dict[str, Any]:
    if task in CLASSIFICATION:
        proba = pipeline.predict_proba(X)
        pred = np.asarray(pipeline.classes_)[proba.argmax(axis=1)]
        return classification_metrics(y, pred, proba, classes, pos_label)
    return regression_metrics(y, pipeline.predict(X), seed=seed)


def _primary_value(pipeline, X, y, task, classes, pos_label, metric: str) -> float | None:
    """Cheap evaluation of just the primary metric (used inside permutation importance)."""
    if task == "regression":
        return float(np.sqrt(mean_squared_error(y, pipeline.predict(X))))
    proba = pipeline.predict_proba(X)
    if metric == "f1_macro":
        pred = np.asarray(pipeline.classes_)[proba.argmax(axis=1)]
        return float(precision_recall_fscore_support(y, pred, average="macro", zero_division=0)[2])
    pos_idx = classes.index(pos_label)
    y_bin = (np.asarray(y) == pos_label).astype(int)
    if metric == "pr_auc":
        return _safe(average_precision_score, y_bin, proba[:, pos_idx])
    return _safe(roc_auc_score, y_bin, proba[:, pos_idx])


# --------------------------------------------------------------------------- #
# Data preparation
# --------------------------------------------------------------------------- #
def _class_label(v: Any) -> Any:
    if pd.isna(v):
        return np.nan
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    return str(v).strip()


def apply_plan(df: pd.DataFrame, plan: list[tuple[str, str]]) -> pd.DataFrame:
    out: dict[str, pd.Series] = {}
    for name, kind in plan:
        col = df[name]
        if kind == "numeric":
            out[name] = to_numeric_clean(col)
        else:
            out[name] = col.map(lambda v: str(v) if pd.notna(v) else np.nan).astype(object)
    return pd.DataFrame(out, index=df.index)


def split_indices(y: pd.Series, task: str, seed: int, test_size: float, val_size: float):
    idx = np.arange(len(y))
    strat = None
    if task in CLASSIFICATION:
        counts = y.value_counts()
        if counts.min() < MIN_PER_CLASS:
            rare = counts.idxmin()
            raise UnsupportedTaskError(
                f"Class '{str(rare)[:30]}' has only {int(counts.min())} row(s); every class needs at least {MIN_PER_CLASS}. "
                "Merge or remove rare classes and try again."
            )
        strat = y.to_numpy()
    trainval, test = train_test_split(idx, test_size=test_size, random_state=seed, stratify=strat)
    rel_val = val_size / (1.0 - test_size)
    strat2 = y.to_numpy()[trainval] if strat is not None else None
    train, val = train_test_split(trainval, test_size=rel_val, random_state=seed, stratify=strat2)
    return np.sort(train), np.sort(val), np.sort(test)


def leakage_suspects(X: pd.DataFrame, y: pd.Series, task: str, threshold: float = 0.95) -> list[str]:
    """Flag numeric features that are almost perfectly related to the target (possible leakage)."""
    suspects = []
    if task == "regression":
        targets = {"": pd.to_numeric(y, errors="coerce")}
    else:
        targets = {str(c): (y == c).astype(float) for c in y.unique()}
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]):
            continue
        x = X[col]
        if x.nunique() < 2:
            continue
        for t in targets.values():
            r = x.corr(t)
            if r is not None and np.isfinite(r) and abs(r) >= threshold:
                suspects.append(col)
                break
    return suspects


def correlated_pairs(X: pd.DataFrame, threshold: float = 0.8) -> list[dict]:
    num = X.select_dtypes(include=[np.number])
    if num.shape[1] < 2:
        return []
    corr = num.corr().abs()
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if np.isfinite(v) and v >= threshold:
                pairs.append({"a": cols[i], "b": cols[j], "abs_correlation": round(float(v), 3)})
    return pairs


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def train_experiment(
    df: pd.DataFrame,
    cfg: TrainConfig,
    *,
    dataset_fingerprint: str | None = None,
    progress: Progress | None = None,
) -> TrainingResult:
    cfg.validate()
    emit: Progress = progress or (lambda stage, frac: None)
    emit("preparing", 0.02)
    if cfg.target not in df.columns:
        raise DataValidationError(f"Target column '{cfg.target[:60]}' was not found in the dataset.", code="target_not_found")
    task, notes = infer_task(df[cfg.target], cfg.task)
    warnings: list[str] = list(notes)

    if task == "regression":
        y_all = to_numeric_clean(df[cfg.target])
    else:
        y_all = df[cfg.target].map(_class_label)
    keep = y_all.notna()
    dropped = int((~keep).sum())
    if dropped:
        warnings.append(f"{dropped} row(s) with a missing or invalid target were removed.")
    if int(keep.sum()) < MIN_ROWS:
        raise DataValidationError(f"At least {MIN_ROWS} rows with a valid target are required (found {int(keep.sum())}).", code="too_few_rows")
    work = df.loc[keep].reset_index(drop=True)
    y = y_all.loc[keep].reset_index(drop=True)

    plan, excluded = plan_features(work, cfg.target, cfg.exclude_columns)
    if not plan:
        raise DataValidationError("No usable feature columns remain after excluding identifiers, text and constant columns.", code="no_features")
    X = apply_plan(work, plan)
    if excluded:
        warnings.append(f"{len(excluded)} column(s) were not used as features: " + ", ".join(sorted(excluded)[:8]) + ".")

    classes: list[str] = []
    pos_label: str | None = None
    if task in CLASSIFICATION:
        classes = sorted(y.unique().tolist())
        if task == "binary":
            if cfg.positive_label is not None:
                if str(cfg.positive_label) not in classes:
                    raise DataValidationError(f"positive_label '{str(cfg.positive_label)[:30]}' is not one of the classes {classes}.")
                pos_label = str(cfg.positive_label)
            else:
                share = y.value_counts(normalize=True)
                pos_label = str(share.idxmin()) if share.iloc[0] != share.iloc[-1] else classes[1]
        shares = y.value_counts(normalize=True)
        if shares.min() < 0.1:
            warnings.append(f"Class imbalance: the rarest class is {100 * shares.min():.1f}% of rows; accuracy alone is misleading.")
    if len(work) < 200:
        warnings.append("Small dataset (< 200 usable rows): metrics have wide uncertainty.")

    emit("splitting", 0.06)
    tr, va, te = split_indices(y, task, cfg.seed, cfg.test_size, cfg.val_size)
    X_tr, X_va, X_te = X.iloc[tr], X.iloc[va], X.iloc[te]
    y_tr, y_va, y_te = y.iloc[tr], y.iloc[va], y.iloc[te]

    suspects = leakage_suspects(X_tr, y_tr, task)
    if suspects:
        warnings.append("Possible target leakage: " + ", ".join(suspects) + " is almost perfectly related to the target. Check how it is produced.")

    spec = primary_metric_spec(task, y_tr)
    zoo = model_zoo(task, cfg.seed, cfg.n_jobs)
    names = cfg.model_names or list(zoo)
    unknown = [n for n in names if n not in zoo]
    if unknown:
        raise DataValidationError(f"Unknown model(s): {', '.join(unknown)}. Available for this task: {', '.join(zoo)}.", code="unknown_model")

    candidates: list[dict] = []
    fitted: dict[str, Pipeline] = {}
    for i, name in enumerate(names):
        emit(f"training {name}", 0.1 + 0.6 * i / len(names))
        pipe = make_pipeline(plan, zoo[name]())
        t0 = time.perf_counter()
        pipe.fit(X_tr, y_tr)
        fit_s = time.perf_counter() - t0
        metrics = evaluate(pipe, X_va, y_va, task, classes, pos_label, cfg.seed)
        fitted[name] = pipe
        candidates.append({"name": name, "fit_seconds": round(fit_s, 3), "validation": metrics})

    # Selection uses VALIDATION metrics only.
    best = max(candidates, key=lambda c: _oriented(c["validation"].get(spec["name"]), spec))
    selected_name = best["name"]
    for c in candidates:
        c["selected"] = c["name"] == selected_name
    pipeline = fitted[selected_name]

    emit("evaluating", 0.75)
    base = make_pipeline(plan, baseline_estimator(task)).fit(X_tr, y_tr)
    baseline = {
        "name": "baseline_prior" if task in CLASSIFICATION else "baseline_mean",
        "validation": evaluate(base, X_va, y_va, task, classes, pos_label, cfg.seed),
        "test": evaluate(base, X_te, y_te, task, classes, pos_label, cfg.seed),
    }
    test_metrics = evaluate(pipeline, X_te, y_te, task, classes, pos_label, cfg.seed)  # evaluated once, after selection
    train_primary = _primary_value(pipeline, X_tr, y_tr, task, classes, pos_label, spec["name"])
    val_primary = best["validation"].get(spec["name"])
    if val_primary is not None and train_primary is not None:
        if spec["direction"] == "higher" and train_primary - val_primary > 0.15:
            warnings.append("The selected model scores much higher on training than validation data: possible overfitting.")
        if spec["direction"] == "lower" and val_primary > 2.5 * train_primary:
            warnings.append("Validation error is much higher than training error: possible overfitting.")
        base_val = baseline["validation"].get(spec["name"])
        if base_val is not None and _oriented(val_primary, spec) <= _oriented(base_val, spec):
            warnings.append("The selected model does not beat the baseline on validation data; predictions add little value.")

    interval = None
    if task == "regression":
        abs_res = np.abs(np.asarray(y_va, dtype=float) - pipeline.predict(X_va))
        n = len(abs_res)
        level = min(1.0, math.ceil((n + 1) * INTERVAL_LEVEL) / n)
        interval = {"level": INTERVAL_LEVEL, "half_width": float(np.quantile(abs_res, level, method="higher")), "method": "split-conformal on validation residuals"}

    emit("explaining", 0.85)
    metric_name = spec["name"]
    sign = -1.0 if spec["direction"] == "lower" else 1.0

    def scorer(est, Xs, ys):
        v = _primary_value(est, Xs, ys, task, classes, pos_label, metric_name)
        return sign * (v if v is not None else 0.0)

    pi = permutation_importance(pipeline, X_va, y_va, scoring=scorer, n_repeats=cfg.importance_repeats, random_state=cfg.seed, n_jobs=1)
    importance = []
    for j, col in enumerate(X_va.columns):
        mean, std = float(pi.importances_mean[j]), float(pi.importances_std[j])
        importance.append({
            "feature": col,
            "importance": mean,
            "std": std,
            "unstable": bool(abs(mean) < 2 * std),
        })
    importance.sort(key=lambda d: d["importance"], reverse=True)
    pairs = correlated_pairs(X_tr)
    explain_warnings = [
        "Importance and explanations describe how this model behaves, not what causes the outcome.",
        "Features that are correlated share credit, so each one's importance can be understated.",
    ]
    if pairs:
        explain_warnings.append("Strongly correlated feature pairs: " + ", ".join(f"{p['a']}/{p['b']}" for p in pairs[:5]) + ".")
    if any(i["unstable"] for i in importance):
        explain_warnings.append("Importance of some features is within noise (marked unstable); do not rank them against each other.")

    schema = fit_schema(plan, X_tr, target=cfg.target, task=task, classes=classes, positive_label=pos_label, excluded=excluded)
    bg_n = min(cfg.background_size, len(X_tr))
    background = X_tr.sample(n=bg_n, random_state=cfg.seed).reset_index(drop=True) if bg_n else X_tr.head(0)

    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "model_name": selected_name,
        "task": task,
        "target": cfg.target,
        "classes": classes,
        "positive_label": pos_label,
        "primary_metric": spec,
        "interval": interval,
        "trained_at": now,
        "app_version": __version__,
        "feature_names": schema.feature_names,
    }
    summary = {
        "experiment_record": {
            "dataset_fingerprint": dataset_fingerprint,
            "target": cfg.target,
            "task": task,
            "seed": cfg.seed,
            "selected_model": selected_name,
            "trained_at": now,
            "software": software_versions(),
        },
        "task": task,
        "target": cfg.target,
        "classes": classes,
        "positive_label": pos_label,
        "seed": cfg.seed,
        "split": {
            "n_train": int(len(tr)), "n_validation": int(len(va)), "n_test": int(len(te)),
            "stratified": task in CLASSIFICATION,
            "selection_split": "validation",
            "test_evaluated_once": True,
        },
        "rows_used": int(len(work)),
        "rows_dropped_missing_target": dropped,
        "features": schema.feature_names,
        "excluded_features": excluded,
        "primary_metric": spec,
        "candidates": candidates,
        "selected_model": selected_name,
        "baseline": baseline,
        "test_metrics": test_metrics,
        "train_primary": train_primary,
        "interval": interval,
        "importance": importance,
        "explanation_warnings": explain_warnings,
        "warnings": warnings,
        "limitations": [
            "Metrics come from a single random split; they carry sampling uncertainty.",
            "Predictions are probabilistic estimates, not guarantees.",
            "The model only reflects patterns in the training data and may not hold for different populations or time periods.",
            "Check fairness and bias separately; this tool does not assess them.",
        ],
    }
    emit("done", 1.0)
    return TrainingResult(ModelBundle(pipeline, schema, metadata, background), jsonable(summary))


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #
def _records_to_frame(records, max_records: int) -> pd.DataFrame:
    if isinstance(records, pd.DataFrame):
        df = records
    else:
        if not isinstance(records, list) or not records:
            raise PredictionInputError("Provide a non-empty list of records.", code="no_records")
        if not all(isinstance(r, dict) for r in records):
            raise PredictionInputError("Each record must be an object of column/value pairs.", code="bad_records")
        df = pd.DataFrame.from_records(records)
    if len(df) == 0:
        raise PredictionInputError("Provide at least one record.", code="no_records")
    if len(df) > max_records:
        raise PredictionInputError(f"At most {max_records} records can be predicted per request.", code="too_many_records")
    return df


def predict_records(bundle: ModelBundle, records, *, max_records: int = 1000) -> dict[str, Any]:
    df = _records_to_frame(records, max_records)
    X, issues = bundle.schema.coerce(df)
    task = bundle.metadata["task"]
    preds: list[dict] = []
    if task in CLASSIFICATION:
        proba = bundle.pipeline.predict_proba(X)
        classes = [str(c) for c in bundle.pipeline.classes_]
        for row in proba:
            k = int(row.argmax())
            conf = float(row[k])
            preds.append({
                "prediction": classes[k],
                "confidence": round(conf, 4),
                "low_confidence": bool(conf < LOW_CONFIDENCE),
                "probabilities": {c: round(float(p), 4) for c, p in zip(classes, row)},
            })
        note = f"Probabilities are model estimates and have not been calibrated; confidence below {LOW_CONFIDENCE:.0%} is flagged."
    else:
        values = bundle.pipeline.predict(X)
        interval = bundle.metadata.get("interval") or {}
        hw = interval.get("half_width")
        for v in values:
            item = {"prediction": round(float(v), 6)}
            if hw is not None:
                item["interval_low"] = round(float(v) - hw, 6)
                item["interval_high"] = round(float(v) + hw, 6)
            preds.append(item)
        note = (
            f"Intervals target about {int(INTERVAL_LEVEL * 100)}% coverage for records similar to the validation data "
            "(split-conformal); they are not guarantees, especially for unusual inputs."
        )
    return jsonable({
        "model": {"name": bundle.metadata["model_name"], "task": task, "target": bundle.metadata["target"]},
        "n_records": int(len(df)),
        "predictions": preds,
        "issues": issues,
        "uncertainty_note": note,
    })


def predictions_frame(bundle: ModelBundle, df: pd.DataFrame, *, max_records: int = 100_000) -> pd.DataFrame:
    """Input rows plus prediction columns, for CSV export."""
    result = predict_records(bundle, df, max_records=max_records)
    out = df.reset_index(drop=True).copy()
    preds = result["predictions"]
    out["prediction"] = [p["prediction"] for p in preds]
    if bundle.metadata["task"] in CLASSIFICATION:
        out["confidence"] = [p["confidence"] for p in preds]
        out["low_confidence"] = [p["low_confidence"] for p in preds]
    elif preds and "interval_low" in preds[0]:
        out["interval_low"] = [p["interval_low"] for p in preds]
        out["interval_high"] = [p["interval_high"] for p in preds]
    return out
