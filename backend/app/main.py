"""Application factory. Run with:  uvicorn --factory app.main:create_app"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api.router import api_router
from .core.config import Settings
from .core.errors import NexusError
from .core.logging import configure_logging, request_id_var
from .db.migrate import upgrade_to_head
from .db.session import Database
from .ml.errors import MLError
from .security.ratelimit import RateLimiter
from .services.datasets import purge_expired
from .services.experiments import mark_interrupted
from .services.jobs import JobRunner

logger = logging.getLogger("nexus")

ML_STATUS = {"artifact_missing": 404, "artifact_corrupt": 500, "artifact_unreadable": 500, "dataset_corrupt": 500}


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Reject oversized request bodies early (declared or streamed) with HTTP 413."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def _reject(self, send) -> None:
        body = b'{"error":{"code":"payload_too_large","message":"The request body is too large.","details":{}}}'
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            return await self._reject(send)
        received, started = 0, False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge()
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._reject(send)


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}, "request_id": request_id_var.get()}},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    problems = settings.problems()
    if problems:
        raise RuntimeError("Invalid configuration: " + " ".join(problems))
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.datasets_dir.mkdir(parents=True, exist_ok=True)
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        if settings.run_migrations:
            upgrade_to_head(settings.database_url, settings.migrations_dir)
        db = Database(settings.database_url)
        jobs = JobRunner(db, settings)
        app.state.db, app.state.jobs = db, jobs
        interrupted = mark_interrupted(db)
        with db.session() as s:
            purged = purge_expired(s, settings)
        logger.info("startup complete", extra={"database": settings.safe_database_url, "interrupted_jobs": interrupted, "expired_datasets_purged": purged, "env": settings.env})
        try:
            yield
        finally:
            jobs.shutdown()
            db.dispose()

    app = FastAPI(
        title="NEXUS AI API",
        version=__version__,
        description="Decision-support API: dataset profiling, model training, predictions, explanations, anomaly detection and drift monitoring. "
        "Predictions are probabilistic estimates, not guarantees.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    limiter = RateLimiter(settings.rate_limit_per_minute)

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
        expose_headers=["X-Request-ID", "Content-Disposition"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")
        rid = rid if rid.isalnum() and len(rid) <= 64 else uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            if request.url.path != "/api/v1/health":
                client = request.client.host if request.client else "unknown"
                if settings.trust_proxy_headers:
                    client = request.headers.get("x-forwarded-for", client).split(",")[0].strip() or client
                allowed, retry = limiter.check(client)
                if not allowed:
                    resp = _error(429, "rate_limited", "Too many requests. Please slow down.")
                    resp.headers["Retry-After"] = str(retry)
                    resp.headers["X-Request-ID"] = rid
                    return resp
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(NexusError)
    async def nexus_error(_: Request, exc: NexusError):
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(MLError)
    async def ml_error(_: Request, exc: MLError):
        return _error(ML_STATUS.get(exc.code, 422), exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"loc": [str(p) for p in e.get("loc", [])], "message": e.get("msg", "invalid")} for e in exc.errors()][:20]
        return _error(422, "validation_error", "The request was not valid.", {"errors": details})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error")
        return _error(500, "internal_error", "An unexpected error occurred. Quote the request id when reporting this.")

    app.include_router(api_router)
    return app
