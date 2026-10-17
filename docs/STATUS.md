# Implemented, optional and not included

"Verified here" means the check was actually executed during development; see [VERIFICATION.md](VERIFICATION.md) for commands and results.

| Feature | Status | Verified here |
|---|---|---|
| CSV ingestion, validation, profiling, quality report | Implemented | Yes (unit tests) |
| Target suggestion and task inference (binary, multiclass, regression) | Implemented | Yes |
| Train/validation/test splits, seeds, leakage controls, baselines, model comparison | Implemented | Yes, including mutation checks |
| Metrics, residual analysis, prediction intervals, low-confidence flags | Implemented | Yes |
| Predictions with the training pipeline, CSV scoring, CSV export with formula protection | Implemented | ML layer yes; HTTP endpoints no |
| Global importance and local Shapley explanations | Implemented | Yes |
| Isolation Forest anomalies, configurable sensitivity, CSV export | Implemented | ML layer yes; HTTP endpoints no |
| Quality and drift analysis with configurable thresholds | Implemented | ML layer yes; HTTP endpoints no |
| Experiment tracking, dataset fingerprint, versions, model checksums, HTML report | Implemented | ML layer yes; persistence no |
| SQL schema, parameterised queries, constraints, cascades | Implemented | Yes (SQLite) |
| SQLAlchemy models, Alembic migration, PostgreSQL support | Implemented | **No** (SQLAlchemy and Alembic were not installable offline) |
| FastAPI service, auth, rate limiting, upload limits, retention, background jobs | Implemented | Config, token, rate-limiter and file-safety logic yes; the running service **no** |
| API integration, security and DB/migration tests | Written | **Not executed** |
| React UI (10 pages), API client, formatters, chart maths | Implemented | Library logic tests yes; components **not rendered**, type-check only against stub React types |
| Frontend component tests | Written | **Not executed** |
| C++ accelerator, tests with sanitizers, benchmark | Implemented, **optional** | Yes |
| Docker images, Compose stack, CI workflows | Written | **No** (YAML parsed only; nothing built or run) |
| Backup and restore scripts | Written | Syntax only |
| Synthetic dataset, fixtures, data card | Implemented | Yes (reproducible hash, passes validation) |

## Optional integrations

* Native C++ accelerator: built with `make accel`, never required.
* PostgreSQL: used by the Compose stack and recommended for production; SQLite is the local default.
* No LLM, embedding service or paid API is used or needed.

## Not included (and why)

| Item | Reason |
|---|---|
| Java 21 Spring Boot orchestrator | Optional in the brief; the in-process runner covers the current workload and a second service would add maintenance without a measured benefit. A queue-backed worker is the natural first step if you scale out. |
| XGBoost, SHAP | Optional; scikit-learn models and a model-agnostic Shapley estimator cover the requirements without extra heavy dependencies. |
| Probability calibration, cross-validation, hyperparameter search | Roadmap items. |
| Per-user accounts and data isolation | Not built; token auth only. See the security limits. |
| Kubernetes, distributed queues | No demonstrated need. |
| Playwright end-to-end tests | The main workflow is covered by API-level tests; browser end-to-end tests were not written. |
| Cloud provider blueprints | None were tested, so none are shipped. |
