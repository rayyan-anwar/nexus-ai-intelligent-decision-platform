from conftest import wait_for


def test_full_training_prediction_explanation_workflow(client, demo, trained_churn):
    exp_id, model_id = trained_churn["id"], trained_churn["model_id"]
    assert model_id

    metrics = client.get(f"/api/v1/experiments/{exp_id}/metrics").json()
    assert metrics["task"] == "binary" and metrics["split"]["test_evaluated_once"] is True
    assert {"roc_auc", "pr_auc", "confusion_matrix"} <= set(metrics["test_metrics"])

    detail = client.get(f"/api/v1/models/{model_id}").json()
    features = {f["name"]: f for f in detail["schema"]["features"]}
    record = {n: (f["median"] if f["kind"] == "numeric" else f["mode"]) for n, f in features.items()}

    pred = client.post(f"/api/v1/models/{model_id}/predict", json={"records": [record]})
    assert pred.status_code == 200, pred.text
    p = pred.json()["predictions"][0]
    assert set(p) == {"prediction", "confidence", "low_confidence", "probabilities"}
    assert pred.json()["uncertainty_note"]

    g = client.get(f"/api/v1/models/{model_id}/explanations").json()
    assert g["importance"] and "causal" in g["interpretation"].lower()
    loc = client.post(f"/api/v1/models/{model_id}/explanations/local", json={"record": record, "n_permutations": 5}).json()
    assert abs(loc["base_value"] + loc["sum_of_contributions"] - loc["model_output"]) < 1e-6

    report = client.get(f"/api/v1/experiments/{exp_id}/report")
    assert report.status_code == 200 and "text/html" in report.headers["content-type"]
    assert "default-src 'none'" in report.headers["content-security-policy"]
    assert "Limitations" in report.text

    assert any(m["id"] == model_id for m in client.get("/api/v1/models").json())
    assert client.delete(f"/api/v1/models/{model_id}").status_code == 204
    assert client.post(f"/api/v1/models/{model_id}/predict", json={"records": [record]}).status_code == 404


def test_predict_csv_returns_predictions_and_neutralises_formulas(client, trained_churn):
    model_id = trained_churn["model_id"]
    csv = b"region,plan,industry,tenure_months,seats,monthly_usage_hours,support_tickets_90d,late_payments_12m,avg_satisfaction\nNorth,basic,=cmd|' /C calc'!A0,10,5,30,1,0,4\n"
    r = client.post(f"/api/v1/models/{model_id}/predict/csv", files={"file": ("new.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "prediction" in r.text.splitlines()[0]
    assert "'=cmd" in r.text and ",=cmd" not in r.text


def test_prediction_validation_errors(client, trained_churn):
    mid = trained_churn["model_id"]
    assert client.post(f"/api/v1/models/{mid}/predict", json={"records": []}).status_code == 422
    assert client.post(f"/api/v1/models/{mid}/predict", json={"records": [{}]}).status_code == 422
    assert client.post(f"/api/v1/models/{mid}/predict", json={"records": [{"seats": 1}], "extra": 1}).status_code == 422


def test_unsupported_and_invalid_experiments_fail_fast(client, demo):
    base = {"dataset_id": demo["id"]}
    r = client.post("/api/v1/experiments", json={**base, "target": "account_id"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_task"
    r = client.post("/api/v1/experiments", json={**base, "target": "no_such_column"})
    assert r.status_code == 422
    r = client.post("/api/v1/experiments", json={**base, "target": "churned", "test_size": 0.9})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post("/api/v1/experiments", json={**base, "target": "churned", "surprise": True})
    assert r.status_code == 422


def test_experiment_not_ready_and_compare(client, demo, trained_churn):
    r = client.post("/api/v1/experiments", json={"dataset_id": demo["id"], "target": "monthly_spend", "exclude_columns": ["churned", "risk_tier"], "model_names": ["linear_regression"]})
    second = wait_for(client, r.json()["id"])
    assert second["status"] == "succeeded"
    cmp = client.get("/api/v1/experiments/compare", params={"ids": f"{trained_churn['id']},{second['id']}"}).json()
    assert len(cmp["experiments"]) == 2 and cmp["notes"]  # different targets -> warning note
    assert client.get("/api/v1/experiments/compare", params={"ids": trained_churn["id"]}).status_code == 422


def test_failed_experiment_reports_safe_message(client, demo):
    r = client.post("/api/v1/experiments", json={"dataset_id": demo["id"], "target": "churned", "exclude_columns": [c["name"] for c in client.get(f"/api/v1/datasets/{demo['id']}/profile").json()["profile"]["columns"] if c["name"] != "churned"]})
    exp = wait_for(client, r.json()["id"])
    assert exp["status"] == "failed" and exp["error_message"]
    assert "Traceback" not in exp["error_message"]
    assert client.get(f"/api/v1/experiments/{exp['id']}/metrics").status_code == 409
