"""Shared deterministic fixtures for the ML tests (no network, no randomness beyond fixed seeds)."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.pipeline import TrainConfig, train_experiment  # noqa: E402
from app.ml.synthetic import generate_accounts  # noqa: E402


@lru_cache(maxsize=1)
def accounts(n: int = 900):
    return generate_accounts(n_rows=n, seed=42)


def churn_frame():
    df, _ = accounts()
    return df.drop(columns=["risk_tier", "monthly_spend"])


def spend_frame():
    df, _ = accounts()
    return df.drop(columns=["risk_tier", "churned"])


def tier_frame():
    df, _ = accounts()
    return df.drop(columns=["churned", "monthly_spend"])


@lru_cache(maxsize=4)
def trained(target: str):
    frames = {"churned": churn_frame, "monthly_spend": spend_frame, "risk_tier": tier_frame}
    return train_experiment(frames[target](), TrainConfig(target=target, seed=42))
