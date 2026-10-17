# Changelog

All notable changes are recorded here. The format follows Keep a Changelog; versions follow Semantic Versioning.

## [Unreleased]

## [0.1.0] - first version

### Added
* Tabular ML core: CSV ingestion and validation, profiling, data-quality report, task inference, leakage-aware training with validation-based model selection and a once-evaluated test split, baselines, prediction with uncertainty, permutation importance, Monte-Carlo Shapley local explanations, Isolation Forest anomaly detection, PSI/KS/chi-square drift analysis, HTML reports, checksummed model artifacts.
* FastAPI service with versioned routes, token authentication, rate limiting, upload limits, retention policy, audit trail and background training jobs; SQLAlchemy models and an Alembic migration (SQLite and PostgreSQL).
* React + TypeScript UI with ten pages and an uncertainty-first prediction display.
* Optional C++ accelerator (ctypes) with NumPy fallback and a benchmark.
* Synthetic data generator, sample dataset, data card and test fixtures.
* Docker, Docker Compose (development and production override), GitHub Actions CI, Makefile, backup and restore scripts, full documentation.

### Not included
* Java orchestration service, XGBoost and SHAP backends, calibration, cross-validation. See [docs/STATUS.md](docs/STATUS.md).
