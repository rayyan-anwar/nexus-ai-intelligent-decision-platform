"""Structured JSON logging with secret redaction."""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

SENSITIVE_FRAGMENTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "cookie", "database_url")
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def redact(value: Any) -> Any:
    """Mask values whose key looks sensitive; recurse into containers."""
    if isinstance(value, dict):
        return {
            k: "***" if any(f in str(k).lower() for f in SENSITIVE_FRAGMENTS) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD}
        payload.update(redact(extras))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
