# API reference

Base path `/api/v1`. Interactive OpenAPI docs are served at `/api/docs` and the schema at `/api/openapi.json`.

## Conventions

* **Auth.** When tokens are configured (always in production) send `Authorization: Bearer <token>`. `GET /health` is public. Admin endpoints need an admin token. See [security](security.md).
* **Errors** use one envelope: `{"error": {"code", "message", "details", "request_id"}}`. Validation errors list `loc` and `message` only; submitted values are never echoed back.
* **Status codes:** `200/201/202/204` success; `401` missing or bad token; `403` insufficient role; `404` not found; `409` result not ready or experiment failed; `413` body too large; `422` invalid input or unsupported task; `429` rate limited; `500` unexpected (generic message plus request id); `503` health check with the database unavailable.
* Every response carries `X-Request-ID`; quote it when reporting problems.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness and database check (public). |
| `GET /settings` | Limits, retention and feature flags. |
| `GET /datasets` | List datasets. |
| `POST /datasets/upload` | Multipart CSV upload (`file`). 201 with dataset metadata. |
| `POST /datasets/demo` | Create a dataset from the bundled **synthetic** sample. |
| `GET /datasets/{id}` | Metadata. |
| `GET /datasets/{id}/profile` | Column profile plus ranked target suggestions (to be confirmed by the user). |
| `GET /datasets/{id}/quality` | Missing values, duplicates, invalid numeric entries, outliers. |
| `GET /datasets/{id}/preview?rows=50` | First rows (max 200). |
| `DELETE /datasets/{id}` | Deletes the dataset file, its experiments and models, and their files. |
| `POST /experiments` | Start training in the background. 202. |
| `GET /experiments` | List (latest 200, optional `dataset_id`). |
| `GET /experiments/{id}` | Status, progress, stage, safe error message. |
| `GET /experiments/{id}/metrics` | Full evaluation summary (409 until finished). |
| `GET /experiments/compare?ids=a,b` | Side-by-side summary of 2 to 6 finished experiments. |
| `GET /experiments/{id}/report?download=true` | Self-contained HTML report (served with a restrictive CSP). |
| `GET /models`, `GET /models/{id}` | Models; detail includes the input schema used to build forms. |
| `POST /models/{id}/predict` | Predict for 1 to 1000 records. |
| `POST /models/{id}/predict/csv` | Score an uploaded CSV, returns a CSV with prediction columns. |
| `GET /models/{id}/explanations` | Global permutation importance with interpretation and warnings. |
| `POST /models/{id}/explanations/local` | Monte-Carlo Shapley explanation for one record. |
| `DELETE /models/{id}` | Delete the model and its artifact. |
| `POST /anomalies/detect` | Isolation Forest scores and flagged rows. |
| `POST /anomalies/export` | Flagged rows as CSV. |
| `POST /drift/analyze` | Reference vs new dataset drift report. |
| `POST /admin/retention/purge` | Admin only: delete datasets past their retention deadline. |

## Examples

```bash
API=http://localhost:8000/api/v1
# 1. create a dataset from the synthetic sample
DS=$(curl -s -X POST $API/datasets/demo | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

# 2. train (exclude the other outcome columns, which would leak the answer)
curl -s -X POST $API/experiments -H 'Content-Type: application/json' \
  -d "{\"dataset_id\":\"$DS\",\"target\":\"churned\",\"exclude_columns\":[\"risk_tier\",\"monthly_spend\"]}"

# 3. poll, then read metrics
curl -s $API/experiments/EXPERIMENT_ID
curl -s $API/experiments/EXPERIMENT_ID/metrics

# 4. predict
curl -s -X POST $API/models/MODEL_ID/predict -H 'Content-Type: application/json' \
  -d '{"records":[{"region":"North","plan":"basic","industry":"retail","tenure_months":8,"seats":5,
        "monthly_usage_hours":40,"support_tickets_90d":4,"late_payments_12m":2,"avg_satisfaction":2.5}]}'
```

With tokens enabled add `-H "Authorization: Bearer $TOKEN"` to every call.

### Example prediction response (shape only)

```json
{
  "model": {"name": "random_forest", "task": "binary", "target": "churned"},
  "n_records": 1,
  "predictions": [{"prediction": "1", "confidence": 0.61, "low_confidence": false,
                   "probabilities": {"0": 0.39, "1": 0.61}}],
  "issues": [],
  "uncertainty_note": "Probabilities are model estimates and have not been calibrated; ..."
}
```
