"""API-level errors. Messages are safe to return to clients."""

from __future__ import annotations

from typing import Any


class NexusError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class NotFound(NexusError):
    status_code, code = 404, "not_found"


class Conflict(NexusError):
    status_code, code = 409, "conflict"


class Unauthorized(NexusError):
    status_code, code = 401, "unauthorized"


class Forbidden(NexusError):
    status_code, code = 403, "forbidden"


class PayloadTooLarge(NexusError):
    status_code, code = 413, "payload_too_large"


class Unprocessable(NexusError):
    status_code, code = 422, "unprocessable"


class TooManyRequests(NexusError):
    status_code, code = 429, "rate_limited"
