"""Training-vs-new-data drift analysis.

Indicators
----------
* Population Stability Index (PSI) - effect-size style indicator. Common rules of
  thumb: < 0.1 stable, 0.1-0.25 moderate, > 0.25 significant. These are
  conventions, not theorems; they are configurable here.
* Two-sample Kolmogorov-Smirnov test (numeric). Assumes independent samples and a
  continuous distribution; ties (e.g. integer counts) make p-values conservative.
* Chi-square test of homogeneity (categorical). Needs expected counts >= 5 per cell;
  the result flags when this assumption fails.

With large samples tiny, harmless shifts become "statistically significant", so
the drift level is driven by PSI and p-values are reported alongside (with
Benjamini-Hochberg adjustment across columns).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import accel
from .profiling import infer_kind, to_numeric_clean

EPS = 1e-4


@dataclass
class DriftConfig:
    psi_warn: float = 0.1
    psi_alert: float = 0.25
    p_threshold: float = 0.05
    dataset_share: float = 0.3
    min_samples: int = 30
    bins: int = 10
    unseen_category_share: float = 0.02

    def validate(self) -> None:
        if not 0 < self.psi_warn < self.psi_alert:
            raise ValueError("require 0 < psi_warn < psi_alert")
        if not 0 < self.p_threshold < 1:
            raise ValueError("p_threshold must be in (0, 1)")
        if not 0 < self.dataset_share <= 1:
            raise ValueError("dataset_share must be in (0, 1]")
        if self.bins < 2 or self.min_samples < 2:
            raise ValueError("bins and min_samples must be >= 2")


def psi_from_counts(ref_counts, cur_counts) -> float:
    ref = np.asarray(ref_counts, dtype=float)
    cur = np.asarray(cur_counts, dtype=float)
    if ref.sum() == 0 or cur.sum() == 0:
        return float("nan")
    p = np.clip(ref / ref.sum(), EPS, None)
    q = np.clip(cur / cur.sum(), EPS, None)
    return float(np.sum((q - p) * np.log(q / p)))


def benjamini_hochberg(pvalues) -> list[float]:
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.clip(adjusted, 0, 1)
    return out.tolist()


def _level(psi: float, cfg: DriftConfig) -> str:
    if np.isnan(psi):
        return "insufficient_data"
    if psi < cfg.psi_warn:
        return "stable"
    return "moderate" if psi < cfg.psi_alert else "significant"


def _num(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else float(v)


def _numeric_drift(ref: pd.Series, cur: pd.Series, cfg: DriftConfig) -> dict:
    r_all, c_all = to_numeric_clean(ref), to_numeric_clean(cur)
    r, c = r_all.dropna().to_numpy(), c_all.dropna().to_numpy()
    out = {
        "type": "numeric",
        "n_reference": int(len(r)),
        "n_current": int(len(c)),
        "missing_rate_reference": round(float(r_all.isna().mean()), 4),
        "missing_rate_current": round(float(c_all.isna().mean()), 4),
        "notes": [],
    }
    if len(r) < cfg.min_samples or len(c) < cfg.min_samples:
        out.update(psi=None, ks_statistic=None, p_value=None, mean_shift_std=None, level="insufficient_data")
        out["notes"].append(f"Fewer than {cfg.min_samples} non-missing values in one of the samples.")
        return out
    inner = np.unique(np.quantile(r, np.linspace(0, 1, cfg.bins + 1)[1:-1]))
    if inner.size == 0:
        inner = np.array([float(r[0])])
        out["notes"].append("Reference column is (nearly) constant; PSI is coarse.")
    psi = psi_from_counts(accel.bin_counts(r, inner), accel.bin_counts(c, inner))
    ks = stats.ks_2samp(r, c)
    std_r = float(np.std(r, ddof=1))
    shift = (float(np.mean(c)) - float(np.mean(r))) / std_r if std_r > 0 else None
    out.update(
        psi=_num(psi),
        ks_statistic=_num(ks.statistic),
        p_value=_num(ks.pvalue),
        mean_shift_std=_num(shift),
        reference_mean=_num(np.mean(r)),
        current_mean=_num(np.mean(c)),
        level=_level(psi, cfg),
    )
    return out


def _categorical_drift(ref: pd.Series, cur: pd.Series, cfg: DriftConfig) -> dict:
    r = ref.dropna().astype(str)
    c = cur.dropna().astype(str)
    out = {
        "type": "categorical",
        "n_reference": int(len(r)),
        "n_current": int(len(c)),
        "missing_rate_reference": round(float(ref.isna().mean()), 4),
        "missing_rate_current": round(float(cur.isna().mean()), 4),
        "notes": [],
    }
    if len(r) < cfg.min_samples or len(c) < cfg.min_samples:
        out.update(psi=None, p_value=None, level="insufficient_data", unseen_categories=[])
        out["notes"].append(f"Fewer than {cfg.min_samples} non-missing values in one of the samples.")
        return out
    cats = sorted(set(r.unique()) | set(c.unique()))
    rc = r.value_counts().reindex(cats, fill_value=0).to_numpy()
    cc = c.value_counts().reindex(cats, fill_value=0).to_numpy()
    psi = psi_from_counts(rc, cc)
    seen = set(r.unique())
    unseen = c[~c.isin(seen)]
    unseen_share = float(len(unseen) / len(c))
    unseen_list = [{"value": str(k)[:30], "share": round(v / len(c), 4)} for k, v in unseen.value_counts().head(5).items()]
    p_value = None
    if len(cats) >= 2:
        table = np.vstack([rc, cc])
        chi2, p, _, expected = stats.chi2_contingency(table)
        p_value = _num(p)
        if expected.min() < 5:
            out["notes"].append("Some expected counts are below 5; the chi-square approximation is unreliable.")
    level = _level(psi, cfg)
    if unseen_share > cfg.unseen_category_share and level == "stable":
        level = "moderate"
        out["notes"].append("Level raised because of previously unseen categories.")
    out.update(psi=_num(psi), p_value=p_value, level=level, unseen_categories=unseen_list, unseen_share=round(unseen_share, 4))
    return out


def analyze_drift(reference: pd.DataFrame, current: pd.DataFrame, config: DriftConfig | None = None, columns: list[str] | None = None) -> dict:
    cfg = config or DriftConfig()
    cfg.validate()
    common = [c for c in reference.columns if c in current.columns]
    if columns is not None:
        common = [c for c in common if c in set(columns)]
    results: list[dict] = []
    for name in common:
        kind = infer_kind(reference[name])
        if kind in {"identifier", "text", "datetime", "constant", "empty"}:
            continue
        if kind in {"numeric", "numeric_like"}:
            res = _numeric_drift(reference[name], current[name], cfg)
        else:
            res = _categorical_drift(reference[name], current[name], cfg)
        res["column"] = str(name)
        res["reference_kind"] = kind
        if abs(res["missing_rate_current"] - res["missing_rate_reference"]) > 0.1:
            res["notes"].append("Missing-value rate changed by more than 10 percentage points.")
        results.append(res)

    pvals = [r["p_value"] for r in results if r.get("p_value") is not None]
    adjusted = iter(benjamini_hochberg(pvals))
    for r in results:
        if r.get("p_value") is not None:
            r["p_value_adjusted"] = _num(next(adjusted))
            r["test_significant"] = bool(r["p_value_adjusted"] < cfg.p_threshold)
        else:
            r["p_value_adjusted"] = None
            r["test_significant"] = None

    assessed = [r for r in results if r["level"] != "insufficient_data"]
    drifted = [r for r in assessed if r["level"] != "stable"]
    share = len(drifted) / len(assessed) if assessed else 0.0
    warnings = [
        "PSI thresholds are conventions, not guarantees; judge drift together with domain knowledge.",
        "Statistical tests assume independent samples; with large samples trivial shifts can be significant.",
    ]
    missing_in_current = [c for c in reference.columns if c not in current.columns]
    if missing_in_current:
        warnings.append(f"{len(missing_in_current)} reference column(s) are absent from the new data.")
    results.sort(key=lambda r: (-1 if r["psi"] is None else r["psi"]), reverse=True)
    return {
        "config": {
            "psi_warn": cfg.psi_warn, "psi_alert": cfg.psi_alert, "p_threshold": cfg.p_threshold,
            "dataset_share": cfg.dataset_share, "min_samples": cfg.min_samples, "bins": cfg.bins,
        },
        "n_reference": int(len(reference)),
        "n_current": int(len(current)),
        "columns_analyzed": len(assessed),
        "columns_drifted": len(drifted),
        "share_drifted": round(share, 4),
        "dataset_drift": bool(assessed and share >= cfg.dataset_share),
        "columns": results,
        "warnings": warnings,
        "native_accelerator": accel.native_available(),
    }
