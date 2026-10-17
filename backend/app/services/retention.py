"""Retention helpers (pure functions)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp (stored consistently across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_expiry(now: datetime, retention_days: int) -> datetime | None:
    """``retention_days == 0`` means keep until explicitly deleted."""
    return None if retention_days <= 0 else now + timedelta(days=retention_days)


def is_expired(expires_at: datetime | None, now: datetime) -> bool:
    return expires_at is not None and expires_at < now
