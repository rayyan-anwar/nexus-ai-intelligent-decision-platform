# Cloud deployment parameters

Provider-neutral values for deploying NEXUS AI. No provider-specific blueprint is included because none was tested.

| Component | What to deploy | Key settings |
|---|---|---|
| Database | Managed PostgreSQL 14+ | Daily backups; private network access from the API only |
| API | `backend/Dockerfile` image (context = repo root), **one instance** | `NEXUS_ENV=production`, `NEXUS_DATABASE_URL`, `NEXUS_API_TOKEN_HASHES`, `NEXUS_ADMIN_TOKEN_HASHES`, `NEXUS_CORS_ORIGINS`, `NEXUS_DATA_DIR=/data` on a persistent disk, `NEXUS_TRUST_PROXY_HEADERS=true` if behind the platform proxy |
| UI | `frontend/dist` from `VITE_API_BASE_URL=https://<api-host>/api/v1 npm run build`, or the `frontend/Dockerfile` image | SPA fallback to `index.html` |
| TLS | Platform-managed certificates | Redirect HTTP to HTTPS |

Memory: model training happens inside the API process, so size the instance for your largest dataset (the default upload limit is 10 MB / 200,000 rows). Measure before choosing an instance size; no sizing guidance is claimed here.
