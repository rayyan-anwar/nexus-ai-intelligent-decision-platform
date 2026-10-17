# Deployment

> **Verification status.** The Docker images, Compose files and cloud steps below were written but **not built or run** in the development sandbox (no Docker or network access). Treat the first run on your machine as the real test, and check [VERIFICATION.md](VERIFICATION.md) for exactly what was and was not exercised.

## 1. Run locally without Docker

Prerequisites: Python 3.12 (3.11 to 3.13 are declared; 3.12 was used), Node.js 20+ (22 used in CI), optionally `g++` and `make` for the native accelerator.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
make accel                      # optional; skip if you have no compiler

# terminal 1: API on :8000 (applies migrations on startup, SQLite in backend/var/)
cd backend && uvicorn --factory app.main:create_app --reload

# terminal 2: UI on :5173, proxying /api to :8000
cd frontend && npm install && npm run dev
```

Open http://localhost:5173, then use **Load synthetic demo data** on the Overview page. No account, API key, paid service or external download is needed.

## 2. Run with Docker Compose

```bash
cp .env.example .env            # set POSTGRES_PASSWORD to a real value
make up                         # or: docker compose -f deployment/docker-compose.yml --env-file .env up --build -d
```

The UI is on http://127.0.0.1:8080. The API and PostgreSQL are *not* published to the host; nginx in the frontend container proxies `/api` to the backend, so no CORS setup is needed. Data persists in the `pgdata` and `nexus_data` volumes.

## 3. Production images

```bash
docker build -f backend/Dockerfile -t nexus-backend .      # build context = repo root
docker build -t nexus-frontend frontend
```

The backend image runs as an unprivileged user, includes migrations and the sample data, and builds the optional C++ library in a separate stage. Use the production override to make tokens mandatory and lock down the containers:

```bash
python scripts/create_token.py          # run twice: one user token, one admin token. Keep the tokens; put the hashes in .env
docker compose -f deployment/docker-compose.yml -f deployment/docker-compose.prod.yml --env-file .env up -d
```

Put a TLS-terminating reverse proxy or platform load balancer in front. Run **one** backend instance (see [architecture](architecture.md)).

## 4. PostgreSQL

Set `NEXUS_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`. Use a dedicated database and a role that owns it. Production mode rejects SQLite. Migrations run automatically at startup; to run them yourself set `NEXUS_RUN_MIGRATIONS=false` and run:

```bash
cd backend && NEXUS_DATABASE_URL=... alembic upgrade head
```

## 5. Environment variables

See `.env.example` for every variable with comments. The ones that matter most in production: `NEXUS_ENV=production`, `NEXUS_DATABASE_URL`, `NEXUS_API_TOKEN_HASHES`, `NEXUS_ADMIN_TOKEN_HASHES`, `NEXUS_CORS_ORIGINS`, `NEXUS_RETENTION_DAYS`, `NEXUS_TRUST_PROXY_HEADERS` (true only behind a proxy you control) and `NEXUS_DATA_DIR` (a persistent volume).

## 6. Hosting the pieces separately (cloud)

Any platform that runs a container and offers managed PostgreSQL will do; the UI can be any static host. Provider free tiers and limits change, so **check the provider's current pricing and limits yourself**; this project makes no claim that any particular deployment is free.

Checklist:

1. Create a PostgreSQL database; note the connection string.
2. Deploy the backend image with the environment variables above and a persistent disk mounted at `NEXUS_DATA_DIR`. Without a persistent disk, uploaded datasets and model files disappear on restart (the database rows would then point at missing files).
3. Set `NEXUS_CORS_ORIGINS` to the exact UI origin (for example `https://app.example.com`).
4. Build the UI with the API address: `VITE_API_BASE_URL=https://api.example.com/api/v1 npm run build`, and publish `frontend/dist` to a static host. Single-page-app hosting needs a fallback to `index.html`.
5. Check `GET https://api.example.com/api/v1/health`, then upload a small CSV through the UI.
6. Enable the platform's automatic restarts and database backups.

An example parameter table lives in [deployment/cloud/README.md](../deployment/cloud/README.md).

## 7. Health checks

* `GET /api/v1/health` returns `{"status": "ok", "database": "ok"}` or HTTP 503 when the database is unreachable. It is public and exempt from rate limiting.
* Containers define Docker health checks against it.

## 8. Backups and restore

```bash
./scripts/backup.sh ./dumps                         # SQLite, or set DATABASE_URL for PostgreSQL (needs pg_dump)
./scripts/restore.sh dumps/<db file> dumps/<data tarball>   # stop the API first
```

Backups hold user data and model files: encrypt them and apply your retention policy to them as well. The scripts were syntax-checked (`bash -n`) but not executed against a real database.

## 9. Shutting down and cleaning up

```bash
make down                                            # stops containers, keeps volumes (your data)
docker compose -f deployment/docker-compose.yml --env-file .env down -v   # also DELETES the volumes
```

Delete datasets and models you no longer need from the UI (Dataset explorer, Reports and settings) or through the API; this removes their files too.
