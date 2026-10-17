import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security.tokens import generate_token, hash_token
from conftest import make_settings


@pytest.fixture()
def secured(tmp_path):
    user, admin = generate_token(), generate_token()
    settings = make_settings(tmp_path, NEXUS_API_TOKEN_HASHES=hash_token(user), NEXUS_ADMIN_TOKEN_HASHES=hash_token(admin))
    with TestClient(create_app(settings)) as c:
        yield c, user, admin


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public_but_data_routes_need_a_token(secured):
    c, user, _ = secured
    assert c.get("/api/v1/health").status_code == 200
    r = c.get("/api/v1/datasets")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert c.get("/api/v1/datasets", headers=auth("wrong-token")).status_code == 401
    assert c.get("/api/v1/datasets", headers=auth(user)).status_code == 200


def test_admin_only_endpoints(secured):
    c, user, admin = secured
    assert c.post("/api/v1/admin/retention/purge", headers=auth(user)).status_code == 403
    r = c.post("/api/v1/admin/retention/purge", headers=auth(admin))
    assert r.status_code == 200 and r.json()["datasets_deleted"] == 0


def test_security_headers_and_request_id(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    bad = client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces"})
    assert bad.headers["x-request-id"] != "bad id with spaces"
    assert " " not in bad.headers["x-request-id"]


def test_rate_limit(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, NEXUS_RATE_LIMIT_PER_MINUTE=3))) as c:
        codes = [c.get("/api/v1/settings").status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
        assert c.get("/api/v1/health").status_code == 200  # health is exempt


def test_errors_do_not_leak_internals(client):
    r = client.post("/api/v1/experiments", json={"dataset_id": "x" * 10, "target": "t"})
    text = r.text.lower()
    for leak in ("traceback", "sqlalchemy", "/home/", "select "):
        assert leak not in text


def test_cors_only_allows_configured_origin(client):
    ok = client.options("/api/v1/datasets", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    evil = client.options("/api/v1/datasets", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers


def test_production_refuses_to_start_without_auth(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(make_settings(tmp_path, NEXUS_ENV="production"))


def test_retention_purge_removes_expired_dataset_and_files(tmp_path):
    settings = make_settings(tmp_path, NEXUS_RETENTION_DAYS=1)
    with TestClient(create_app(settings)) as c:
        ds = c.post("/api/v1/datasets/demo").json()
        files = list(settings.datasets_dir.glob("*.csv"))
        assert len(files) == 1
        from datetime import timedelta
        from sqlalchemy import update
        from app.db.models import Dataset
        from app.services.retention import utcnow
        with c.app.state.db.session() as s:
            s.execute(update(Dataset).where(Dataset.id == ds["id"]).values(expires_at=utcnow() - timedelta(days=1)))
        assert c.post("/api/v1/admin/retention/purge").json()["datasets_deleted"] == 1
        assert c.get(f"/api/v1/datasets/{ds['id']}").status_code == 404
        assert not list(settings.datasets_dir.glob("*.csv"))
