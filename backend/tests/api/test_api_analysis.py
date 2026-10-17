from conftest import SAMPLE


def test_anomaly_detection_and_export(client, demo):
    body = {"dataset_id": demo["id"], "sensitivity": "medium"}
    r = client.post("/api/v1/anomalies/detect", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert "scores" not in res and res["n_flagged"] > 0 and "not mean fraud" in res["warning"]
    assert client.post("/api/v1/anomalies/detect", json={**body, "include_scores": True}).json()["scores"]
    csv = client.post("/api/v1/anomalies/export", json=body)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0].startswith("anomaly_score")


def test_anomaly_validation(client, demo):
    assert client.post("/api/v1/anomalies/detect", json={"dataset_id": demo["id"], "sensitivity": 0.9}).status_code == 422
    assert client.post("/api/v1/anomalies/detect", json={"dataset_id": demo["id"], "columns": ["nope"]}).status_code == 422
    assert client.post("/api/v1/anomalies/detect", json={"dataset_id": "missing_id"}).status_code == 404


def test_drift_between_reference_and_shifted_upload(client, demo):
    shifted = (SAMPLE / "fixtures" / "drift_current.csv").read_bytes()
    cur = client.post("/api/v1/datasets/upload", files={"file": ("drift.csv", shifted, "text/csv")}).json()
    r = client.post("/api/v1/drift/analyze", json={"reference_dataset_id": demo["id"], "current_dataset_id": cur["id"]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["dataset_drift"] is True
    levels = {c["column"]: c["level"] for c in res["columns"]}
    assert levels["monthly_usage_hours"] == "significant" and levels["seats"] == "stable"
    same = client.post("/api/v1/drift/analyze", json={"reference_dataset_id": demo["id"], "current_dataset_id": demo["id"]}).json()
    assert same["dataset_drift"] is False


def test_drift_threshold_validation(client, demo):
    bad = {"reference_dataset_id": demo["id"], "current_dataset_id": demo["id"], "thresholds": {"psi_warn": 0.5, "psi_alert": 0.1}}
    r = client.post("/api/v1/drift/analyze", json=bad)
    assert r.status_code == 422
