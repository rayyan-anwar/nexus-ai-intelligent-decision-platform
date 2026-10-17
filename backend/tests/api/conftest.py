"""API test fixtures. Skipped automatically when the web stack is not installed."""

import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SAMPLE = REPO / "data" / "sample"
CHURN_EXCLUDES = ["risk_tier", "monthly_spend"]


def make_settings(tmp_path: Path, **overrides) -> Settings:
    env = {
        "NEXUS_ENV": "test",
        "NEXUS_DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
        "NEXUS_DATA_DIR": str(tmp_path / "var"),
        "NEXUS_SAMPLE_CSV": str(SAMPLE / "nexus_synthetic_accounts.csv"),
        "NEXUS_RATE_LIMIT_PER_MINUTE": "0",
        "NEXUS_LOG_LEVEL": "WARNING",
    }
    env.update({k: str(v) for k, v in overrides.items()})
    return Settings.from_env(env)


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


@pytest.fixture()
def small_upload_client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, NEXUS_MAX_UPLOAD_MB=1))) as c:
        yield c


@pytest.fixture()
def demo(client):
    r = client.post("/api/v1/datasets/demo")
    assert r.status_code == 201, r.text
    return r.json()


def wait_for(client, experiment_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/v1/experiments/{experiment_id}").json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.5)
    raise AssertionError("experiment did not finish in time")


@pytest.fixture()
def trained_churn(client, demo):
    r = client.post("/api/v1/experiments", json={"dataset_id": demo["id"], "target": "churned", "exclude_columns": CHURN_EXCLUDES})
    assert r.status_code == 202, r.text
    exp = wait_for(client, r.json()["id"])
    assert exp["status"] == "succeeded", exp
    return exp
