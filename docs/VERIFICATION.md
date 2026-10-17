# Verification report

This report lists only what was actually executed while building the project, the exact commands, and the real results. Anything not listed under "Executed" was **not** run.

## Environment

The build sandbox had **no network access**, so only pre-installed packages were available: Python 3.12.3, pandas 3.0.2, NumPy 2.4.4, scikit-learn 1.8.0, SciPy 1.17.1, joblib, Node.js v22.22.2, `tsx`, `typescript`, g++ 13.3.0, GNU make. **Not available:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, httpx, ruff, React and its type definitions, Vite, Vitest, ESLint, Docker. Consequently the web service, database layer, React components, Docker images and CI could not be run.

## Executed, with results

| # | Command (from the repository root unless noted) | Result |
|---|---|---|
| 1 | `make -C services/cpp-accelerator clean && make -C services/cpp-accelerator` | Built with `-O3 -Wall -Wextra -Wpedantic`: 0 warnings, 0 errors |
| 2 | `make -C services/cpp-accelerator test` (AddressSanitizer + UBSan) | `all C++ tests passed`, exit code 0 |
| 3 | `cd backend && python3 -m unittest discover -s tests -p "test_*.py"` (native library present) | **Ran 90 tests, OK** |
| 4 | `cd backend && NEXUS_DISABLE_ACCEL=1 python3 -m unittest discover -s tests -p "test_*.py"` | **Ran 90 tests, OK (skipped=3)**: the 3 skipped tests compare native against fallback |
| 5 | `cd frontend && tsx --test src/lib/*.test.ts` | tests 17, pass 17, fail 0 |
| 6 | `python3 scripts/static_check.py backend/app` and `... backend/tests` | 47 files, 0 problems; 14 files, 0 problems (undefined names, unused imports, broken internal imports) |
| 7 | `python3 -m compileall -q backend database scripts data`; `bash -n scripts/*.sh`; YAML parse of workflow, Dependabot and Compose files | All succeeded |
| 8 | Syntax transpile of every `.ts`/`.tsx` file with the TypeScript compiler API | 0 syntax errors |
| 9 | `tsc` over `frontend/src` against **hand-written stub** React types (strict, `noUnusedLocals`, `noUnusedParameters`, `noImplicitAny` relaxed) | Exit 0. This catches wrong property names and unused symbols in project code; it does **not** validate against the real React types |
| 10 | `PYTHONPATH=backend python3 data/generators/generate_sample.py` run twice | Identical SHA-256 of the sample CSV both times; all shipped CSVs pass `load_csv_bytes` |
| 11 | `PYTHONPATH=backend python3 scripts/generate_results.py` | Wrote `docs/results.md` from the actual training, anomaly and drift runs |
| 12 | `make -C services/cpp-accelerator bench` | Results recorded in `docs/benchmarks.md` (1.4x to 1.8x at 1M+ values; slower at 10k) |

### The 90 backend tests by file

| File | Tests | Covers |
|---|---:|---|
| `test_ingest.py` | 8 | Empty, malformed, binary, oversized, duplicate-header uploads; row/column limits; CSV formula injection |
| `test_data_quality.py` | 12 | Generator reproducibility; profiling; quality report on the fixture (invalid types, duplicates, missing, unseen categories); task inference and unsupported targets |
| `test_pipeline.py` | 23 | All three task types; metrics schemas; reproducibility; selection on validation for every task; test split touched only after selection; preprocessing fitted on training rows only; chance-level score on shuffled labels; leakage warning; graceful failures; prediction schema and consistency between batch, single and direct pipeline; input-problem reporting; artifact save/load round trip, tamper and missing-file rejection; fingerprint stability |
| `test_explain_anomaly_drift.py` | 16 | Shapley additivity, determinism, direction sanity, validation; anomaly detection quality, sensitivity ordering, determinism; drift on shifted vs unshifted columns, thresholds, small samples, PSI and Benjamini-Hochberg helpers; report content and HTML escaping |
| `test_accel.py` | 7 | Fallback semantics; native/fallback equivalence (3 tests skip when the library is absent) |
| `test_security_core.py` | 17 | Config validation and production guards; log redaction; token roles; rate limiter; filename and path safety; retention |
| `test_sql_schema.py` | 7 | Schema, every analytical query, injection payload treated as data, constraints, cascades (on SQLite) |

### Checks that the tests can fail

Because all tests passed on the first run, three deliberate bugs were injected and the relevant tests re-run:

1. Selection direction inverted for lower-is-better metrics: **initially not caught** (the selection test only covered a binary task). A test covering all three tasks was added; the mutation is now caught.
2. Shapley contributions scaled by 0.9: caught by the additivity test.
3. Preprocessing refitted on all rows (simulated leakage): caught by the train-only-fit test.

### Defects found during development and fixed

* API test fixture computed the repository root one level too high (found by review; verified the corrected path resolves the sample files).
* A request-id test used a CR/LF header value that HTTP clients may reject before it reaches the app.
* `DriftThresholds` did not enforce `psi_warn < psi_alert`, which would have returned HTTP 500 instead of 422 (found while writing a test; fixed in the schema and in the route).
* `AsyncState<T>` typing mismatch in the React hook (found by the stub type-check).
* The migration runner did not create the SQLite directory before connecting.
* A hand-written sentence in the results generator contradicted its own numbers (precision vs recall); narrative statements in `docs/results.md` are now computed from the data.
* Unused imports in application and test code (found by the static checker).

## Written but NOT executed

| Item | Why not run | What to do |
|---|---|---|
| FastAPI app, routes, middleware, error handlers (`backend/app/api`, `main.py`) | FastAPI/Starlette/Pydantic not installable offline | `pip install -r backend/requirements-dev.txt && cd backend && python -m pytest` |
| SQLAlchemy models, session handling, Alembic migration, services (`backend/app/db`, `services`) | SQLAlchemy/Alembic not installable | Same command; `tests/api/test_db_and_migrations.py` also checks the migration against the ORM metadata |
| API, security and DB tests (`backend/tests/api/`, about 30 tests) | Need the web stack and pytest | Same command. They skip automatically if the stack is missing |
| React components and pages; Vitest component tests | No React, Vite or Vitest | `cd frontend && npm install && npm run typecheck && npm run lint && npm test` |
| ESLint, ruff | Not installed | `make lint` (expect a few findings on the first run) |
| Docker images, Compose stack, production override | No Docker | `make up`; validate first with `docker compose ... config` |
| GitHub Actions workflows | Need GitHub | Push and inspect the Actions tab |
| `backup.sh` / `restore.sh` against a real database | No PostgreSQL; syntax check only | Test on a scratch database |
| Browser behaviour, accessibility audit, responsive layout | No browser run | Manual check; run an automated audit such as axe |
| Dependency vulnerability scans | No network | CI `security` job |
| End-to-end browser tests | Not written | Roadmap |

## Known defects and risks

* The unexecuted layers very likely contain small bugs; the static and stub checks catch only certain classes (undefined names, unused code, wrong property names).
* Declared minimum versions (pandas 3, NumPy 2, scikit-learn 1.8, SciPy 1.14) are the versions tested; no older versions were tried. Frontend dependency ranges are from memory of current releases and were not resolved or installed.
* No lock files exist yet.
* The `churned` demo model is modest on its held-out test split (see `docs/results.md`), with a notable validation-to-test gap; this is documented rather than tuned away.
* In-process rate limiting and job runner mean a single API worker is required.

## Not implemented

See [STATUS.md](STATUS.md): Java orchestrator, XGBoost/SHAP backends, probability calibration, cross-validation, per-user isolation, Playwright end-to-end tests.
