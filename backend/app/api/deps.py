from __future__ import annotations

from typing import Annotated, Iterator

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.errors import Forbidden, Unauthorized
from ..schemas.api import ID_PATTERN
from ..security.tokens import Principal, authenticate

bearer_scheme = HTTPBearer(auto_error=False, description="API token (see docs/security.md)")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.db.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_jobs(request: Request):
    return request.app.state.jobs


def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal:
    if not settings.auth_required:
        return Principal("local", "admin")  # local development without tokens
    header = f"Bearer {creds.credentials}" if creds else None
    principal = authenticate(header, settings.api_token_hashes, settings.admin_token_hashes)
    if principal is None:
        raise Unauthorized("A valid API token is required.")
    return principal


def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.role != "admin":
        raise Forbidden("This action requires an administrator token.")
    return principal


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]
UserDep = Annotated[Principal, Depends(get_principal)]
AdminDep = Annotated[Principal, Depends(require_admin)]
IdPath = Annotated[str, Path(pattern=ID_PATTERN)]
