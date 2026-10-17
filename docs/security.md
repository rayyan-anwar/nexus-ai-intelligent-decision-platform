# Security and privacy

This is a description of the controls in the code and their limits. It is not a compliance assessment; no regulatory compliance (GDPR, HIPAA, SOC 2 or otherwise) is claimed.

## What is implemented

| Area | Control |
|---|---|
| Configuration | Environment variables only (`NEXUS_*`); `.env.example` has placeholders; `.env` is git-ignored. Production refuses to start without token hashes, with wildcard CORS, or on SQLite. |
| Authentication | Bearer tokens. Only SHA-256 hashes are configured; comparison is constant-time. Two roles: *user* and *admin* (purge endpoint). No local user accounts exist, so no passwords are stored. Generate tokens with `python scripts/create_token.py`. |
| Token handling in the UI | Kept in memory only (never `localStorage`), so a reload requires pasting it again. |
| Rate limiting | In-process sliding window per client IP (`NEXUS_RATE_LIMIT_PER_MINUTE`). Health checks are exempt. |
| CORS | Explicit origin list; credentials disabled; limited methods and headers. |
| Uploads | Size limit enforced from `Content-Length` and while streaming (413); row and column limits; UTF-8 text only; header validation; generated stored filenames (the client's name is cosmetic and stripped of path parts); atomic writes; path containment check on every file access. |
| CSV injection | Exported CSV cells starting with `=`, `+`, `-`, `@`, tab or CR are prefixed with a quote. |
| SQL injection | SQLAlchemy with bound parameters; the SQL files use named parameters; a test confirms an injection payload is treated as data. |
| Artifact integrity | Model files are pickled by joblib, which can execute code when loaded. Each file's SHA-256 is recorded at creation and verified before every load; failures raise a safe error. |
| Error handling | Central handlers return an error code, a safe message and a request id; stack traces and SQL stay in server logs. Unexpected training failures store a generic message. |
| Logging | Structured JSON; values under keys like `password`, `token`, `authorization`, `api_key` and `database_url` are masked; dataset values and prediction inputs are never logged. The database URL is logged with the password masked. |
| Prediction history | Only a hash of each request and aggregate counts are stored. |
| Data retention | Datasets expire after `NEXUS_RETENTION_DAYS` (default 30; 0 keeps them until deleted). Expired data is purged on startup and by an admin endpoint; deleting a dataset removes its experiments, models and files. |
| HTTP hardening | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` on API responses; HTML reports are escaped and served with `Content-Security-Policy: default-src 'none'`; nginx adds a CSP for the UI. |
| Containers | Non-root users, health checks, read-only filesystems and dropped capabilities in the production override. |
| Supply chain | Dependency ranges are constrained; CI runs `pip-audit` and `npm audit`; Dependabot is configured. |

## Known limitations (read before deploying)

* **No per-user data isolation.** Any valid token can see every dataset and model on the server. Do not host data for mutually distrusting parties on one deployment.
* **Tokens are bearer secrets.** Serve everything over HTTPS (terminate TLS at a reverse proxy or platform load balancer); this repository does not manage certificates. Rotate by replacing hashes and restarting.
* **Rate limiting is per process** and trusts `X-Forwarded-For` only when `NEXUS_TRUST_PROXY_HEADERS=true`.
* **Model artifacts are only as safe as the data directory.** Anyone who can write both a model file and the matching database checksum can run code. Restrict filesystem and database access.
* Uploaded datasets and model files (which contain a small sample of training rows) are stored unencrypted on disk. Use disk or volume encryption and encrypt backups.
* Backups are not subject to the retention policy automatically; apply your own.
* Training runs inside the API process; a very large upload can still consume significant memory within the configured limits.
* Security tests for the API layer exist but were **not executed in the development sandbox** (see [VERIFICATION.md](VERIFICATION.md)). Run them in CI before relying on them.

## Reporting vulnerabilities

See [../SECURITY.md](../SECURITY.md).
