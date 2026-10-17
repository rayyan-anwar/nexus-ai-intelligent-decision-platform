# Contributing

Thanks for helping improve NEXUS AI. Small, focused pull requests are easiest to review.

## Ground rules

* **No invented results.** Do not add benchmark numbers, test outcomes, badges or claims you have not produced. Tables in `docs/results.md` and `docs/benchmarks.md` come from scripts (`scripts/generate_results.py`, `make bench`); regenerate them rather than editing by hand.
* **No secrets or real data** in commits, fixtures or issues. Use the synthetic generator for test data.
* Every behaviour change needs a test. Prefer tests that would fail if the logic were broken (try breaking the code on purpose once).
* Keep the ML layer (`backend/app/ml`) free of web-framework imports.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd frontend && npm install)
make accel          # optional native library
```

## Checks before opening a pull request

```bash
make test           # backend: pytest (ML, SQL, security, API)
make test-core      # same ML/SQL/security tests without the web stack, standard-library runner
make test-web       # frontend library + component tests
make lint           # ruff, eslint, tsc
make static-check   # offline undefined-name / unused-import check
make accel-test     # C++ tests with sanitizers (if you touched services/cpp-accelerator)
```

## Style

* Python: ruff defaults from `backend/pyproject.toml`; type hints on public functions; docstrings that say *why*.
* TypeScript: strict mode, no `any`, accessible markup (labels, roles, keyboard support).
* Commit messages: short imperative summary, then details if needed.

## Reporting bugs and ideas

Open an issue with steps to reproduce, expected and actual behaviour, and versions. For security problems follow [SECURITY.md](SECURITY.md) instead.
