SAMPLE_CSV = b"a,b,c\n1,x,2.5\n2,y,3.5\n3,x,4.5\n"


def test_health_and_openapi(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["database"] == "ok"
    paths = client.get("/api/openapi.json").json()["paths"]
    for p in [
        "/api/v1/health", "/api/v1/datasets", "/api/v1/datasets/upload", "/api/v1/datasets/{dataset_id}/profile",
        "/api/v1/experiments", "/api/v1/experiments/{experiment_id}", "/api/v1/experiments/{experiment_id}/metrics",
        "/api/v1/experiments/{experiment_id}/report", "/api/v1/models/{model_id}/predict", "/api/v1/anomalies/detect",
        "/api/v1/drift/analyze", "/api/v1/models/{model_id}/explanations",
    ]:
        assert p in paths, p


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) >= {"code", "message"}


def test_demo_dataset_profile_and_quality(client, demo):
    assert demo["is_synthetic"] is True and demo["n_rows"] == 2000
    prof = client.get(f"/api/v1/datasets/{demo['id']}/profile").json()
    assert "churned" in [s["column"] for s in prof["target_suggestions"]]
    q = client.get(f"/api/v1/datasets/{demo['id']}/quality").json()
    assert q["severity_counts"]["error"] == 0
    assert any(d["id"] == demo["id"] for d in client.get("/api/v1/datasets").json())


def test_preview_limits(client, demo):
    body = client.get(f"/api/v1/datasets/{demo['id']}/preview", params={"rows": 5}).json()
    assert len(body["rows"]) == 5 and body["total_rows"] == 2000
    assert client.get(f"/api/v1/datasets/{demo['id']}/preview", params={"rows": 100000}).status_code == 422


def test_upload_valid_csv(client):
    r = client.post("/api/v1/datasets/upload", files={"file": ("../../evil name.csv", SAMPLE_CSV, "text/csv")})
    assert r.status_code == 201
    body = r.json()
    assert body["n_rows"] == 3 and "/" not in body["name"] and ".." not in body["name"]


def test_upload_rejections(client):
    cases = {
        "empty": (b"", "empty_file"),
        "header_only": (b"a,b\n", "no_rows"),
        "binary": (b"\x00\x01\x02\x03", "not_text"),
        "dup_cols": (b"a,a\n1,2\n", "duplicate_columns"),
    }
    for name, (content, code) in cases.items():
        r = client.post("/api/v1/datasets/upload", files={"file": (f"{name}.csv", content, "text/csv")})
        assert r.status_code == 422, name
        assert r.json()["error"]["code"] == code, name


def test_oversized_upload_rejected(small_upload_client):
    big = b"a\n" + b"1\n" * (2 * 1024 * 1024)
    r = small_upload_client.post("/api/v1/datasets/upload", files={"file": ("big.csv", big, "text/csv")})
    assert r.status_code == 413


def test_invalid_id_and_missing_dataset(client):
    assert client.get("/api/v1/datasets/does_not_exist").status_code == 404
    assert client.get("/api/v1/datasets/bad%20id!").status_code == 422


def test_delete_dataset(client, demo):
    assert client.delete(f"/api/v1/datasets/{demo['id']}").status_code == 204
    assert client.get(f"/api/v1/datasets/{demo['id']}").status_code == 404
