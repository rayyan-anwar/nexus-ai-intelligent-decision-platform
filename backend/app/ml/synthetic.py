"""Synthetic dataset generator.

Everything produced here is SYNTHETIC. No real person, company or transaction is
represented. The data is generated from documented, simple probabilistic rules
with a fixed seed so every run is reproducible.

The generated "accounts" table supports:
  * binary classification   -> ``churned``
  * multiclass              -> ``risk_tier``
  * regression              -> ``monthly_spend``
  * anomaly detection       -> injected anomalies (ground truth returned separately)
  * data-quality / drift tests via ``make_quality_fixture`` and ``make_drift_fixture``
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REGIONS = ["North", "South", "East", "West", "Central"]
PLANS = ["basic", "standard", "premium"]
INDUSTRIES = ["retail", "finance", "health", "education", "logistics", "media"]
PLAN_BASE_PRICE = {"basic": 29.0, "standard": 79.0, "premium": 199.0}

COLUMN_DEFINITIONS = {
    "account_id": "Synthetic unique identifier (ACC-000001 ...). Identifier, excluded from modelling.",
    "region": "Categorical. Sales region of the synthetic account.",
    "plan": "Categorical. Subscription plan: basic, standard, premium.",
    "industry": "Categorical. Industry vertical (about 2% missing).",
    "tenure_months": "Integer. Months since the synthetic account was created (1-120).",
    "seats": "Integer. Number of licensed seats (1-200).",
    "monthly_usage_hours": "Float. Average product usage hours per month.",
    "support_tickets_90d": "Integer. Support tickets opened in the last 90 days.",
    "late_payments_12m": "Integer. Late payments in the last 12 months.",
    "avg_satisfaction": "Float 1-5. Average satisfaction score (about 6% missing).",
    "monthly_spend": "Float. Monthly spend in synthetic currency units. Regression target.",
    "churned": "Binary 0/1. Whether the account churned. Binary classification target.",
    "risk_tier": "Categorical low/medium/high. Multiclass target derived from a noisy risk score.",
}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def generate_accounts(
    n_rows: int = 2000, seed: int = 42, anomaly_rate: float = 0.02
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(accounts, anomaly_ground_truth)``.

    ``anomaly_ground_truth`` has columns ``account_id`` and ``is_injected_anomaly``.
    It is kept separate on purpose so it can never leak into model features.
    """
    if n_rows < 50:
        raise ValueError("n_rows must be at least 50")
    if not 0 <= anomaly_rate < 0.5:
        raise ValueError("anomaly_rate must be in [0, 0.5)")
    rng = np.random.default_rng(seed)
    n = n_rows

    region = rng.choice(REGIONS, size=n, p=[0.28, 0.22, 0.2, 0.18, 0.12])
    plan = rng.choice(PLANS, size=n, p=[0.5, 0.3, 0.2])
    industry = rng.choice(INDUSTRIES, size=n)
    plan_idx = pd.Series(plan).map({p: i for i, p in enumerate(PLANS)}).to_numpy()

    tenure = np.clip(rng.gamma(2.2, 14.0, n), 1, 120).round().astype(int)
    seats = np.clip(np.exp(rng.normal(2.2, 1.0, n)), 1, 200).round().astype(int)
    usage = rng.gamma(3.0, 18.0, n) * (1.0 + 0.15 * plan_idx)
    tickets = rng.poisson(1.0 + 0.08 * np.sqrt(seats) + 0.2 * (plan == "basic"), n)
    late = rng.poisson(0.35 + 0.25 * (plan == "basic"), n)
    satisfaction = np.clip(4.3 - 0.22 * tickets + 0.004 * tenure + rng.normal(0, 0.55, n), 1.0, 5.0).round(2)

    spend = (
        pd.Series(plan).map(PLAN_BASE_PRICE).to_numpy()
        + 0.9 * seats * (1 + plan_idx)
        + 0.35 * usage
        + rng.normal(0, 12.0, n)
    ).round(2)

    churn_logit = (
        -1.4
        + 0.35 * tickets
        + 0.55 * late
        - 0.9 * (satisfaction - 3.5)
        - 0.012 * tenure
        - 0.004 * usage
        + 0.4 * (plan == "basic")
        + rng.normal(0, 0.8, n)
    )
    churned = (rng.random(n) < _sigmoid(churn_logit)).astype(int)

    risk_score = 0.5 * tickets + 0.8 * late - 0.6 * (satisfaction - 3.5) - 0.01 * tenure + rng.normal(0, 0.9, n)
    q_low, q_high = np.quantile(risk_score, [0.5, 0.8])
    risk_tier = np.where(risk_score < q_low, "low", np.where(risk_score < q_high, "medium", "high"))

    df = pd.DataFrame(
        {
            "account_id": [f"ACC-{i + 1:06d}" for i in range(n)],
            "region": region,
            "plan": plan,
            "industry": industry,
            "tenure_months": tenure,
            "seats": seats,
            "monthly_usage_hours": usage.round(2),
            "support_tickets_90d": tickets,
            "late_payments_12m": late,
            "avg_satisfaction": satisfaction,
            "monthly_spend": spend,
            "churned": churned,
            "risk_tier": risk_tier,
        }
    )

    # Missing values (MAR: satisfaction is more often missing on the basic plan).
    miss_sat = rng.random(n) < (0.03 + 0.06 * (plan == "basic"))
    df["avg_satisfaction"] = df["avg_satisfaction"].mask(miss_sat)
    df["industry"] = df["industry"].mask(rng.random(n) < 0.02)

    # Injected anomalies (ground truth kept separately).
    is_anom = np.zeros(n, dtype=bool)
    n_anom = int(round(anomaly_rate * n))
    if n_anom:
        idx = rng.choice(n, size=n_anom, replace=False)
        is_anom[idx] = True
        for i in idx:
            kind = rng.integers(0, 4)
            if kind == 0:
                df.loc[i, "monthly_usage_hours"] = round(float(df.loc[i, "monthly_usage_hours"]) * rng.uniform(6, 12), 2)
            elif kind == 1:
                df.loc[i, "monthly_spend"] = round(float(df.loc[i, "monthly_spend"]) * rng.uniform(4, 8), 2)
            elif kind == 2:
                df.loc[i, "support_tickets_90d"] = int(rng.integers(18, 40))
                df.loc[i, "late_payments_12m"] = int(rng.integers(8, 15))
            else:
                df.loc[i, "seats"] = int(rng.integers(400, 900))
                df.loc[i, "tenure_months"] = 1
    truth = pd.DataFrame({"account_id": df["account_id"], "is_injected_anomaly": is_anom})
    return df, truth


def make_quality_fixture(df: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Return a copy with deliberate data-quality problems.

    * ~8% missing ``tenure_months``
    * 10 invalid (non-numeric) ``monthly_usage_hours`` entries
    * 5 rows with the unexpected region ``Atlantis``
    * 15 exact duplicate rows appended
    """
    rng = np.random.default_rng(seed)
    out = df.copy()
    n = len(out)
    out["tenure_months"] = out["tenure_months"].astype(float).mask(rng.random(n) < 0.08)
    usage = out["monthly_usage_hours"].astype(object)
    for i in rng.choice(n, size=10, replace=False):
        usage.iloc[i] = rng.choice(["n/a", "abc", "??"])
    out["monthly_usage_hours"] = usage
    for i in rng.choice(n, size=5, replace=False):
        out.loc[out.index[i], "region"] = "Atlantis"
    dupes = out.iloc[rng.choice(n, size=15, replace=False)]
    return pd.concat([out, dupes], ignore_index=True)


def make_drift_fixture(df: pd.DataFrame, n_rows: int = 600, seed: int = 11) -> pd.DataFrame:
    """Return a resampled frame with deliberate distribution shifts.

    Shifted: ``monthly_usage_hours`` (x1.6), ``support_tickets_90d`` (+2),
    ``plan`` mix (more premium), new region ``Overseas``.
    Unshifted: ``seats``, ``tenure_months``, ``industry``.
    """
    rng = np.random.default_rng(seed)
    out = df.sample(n=n_rows, replace=True, random_state=seed).reset_index(drop=True)
    out["monthly_usage_hours"] = (out["monthly_usage_hours"] * 1.6).round(2)
    out["support_tickets_90d"] = out["support_tickets_90d"] + 2
    premium = rng.random(n_rows) < 0.45
    out.loc[premium, "plan"] = "premium"
    overseas = rng.random(n_rows) < 0.08
    out.loc[overseas, "region"] = "Overseas"
    return out
