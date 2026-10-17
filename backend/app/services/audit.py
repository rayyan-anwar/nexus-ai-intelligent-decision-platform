from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..core.logging import redact
from ..db.models import AuditEvent
from ..ml.tracking import jsonable
from .retention import utcnow


def record_audit(db: Session, actor: str, action: str, resource_type: str, resource_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    """Append an audit event (caller commits). Details are redacted and must never contain raw data."""
    db.add(
        AuditEvent(
            occurred_at=utcnow(),
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail_json=jsonable(redact(detail)) if detail else None,
        )
    )
