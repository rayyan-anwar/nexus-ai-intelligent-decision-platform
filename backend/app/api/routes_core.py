"""Health, settings and admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from .. import __version__
from ..ml import accel
from ..schemas.api import HealthOut, PurgeOut, SettingsOut
from ..services.datasets import purge_expired
from .deps import AdminDep, SessionDep, SettingsDep, UserDep, get_principal

public = APIRouter(tags=["health"])
router = APIRouter(dependencies=[Depends(get_principal)])


@public.get("/health", response_model=HealthOut, summary="Liveness and database check")
def health(request: Request, response: Response) -> HealthOut:
    ok = request.app.state.db.ping()
    if not ok:
        response.status_code = 503
    return HealthOut(status="ok" if ok else "degraded", version=__version__, database="ok" if ok else "unavailable")


@router.get("/settings", response_model=SettingsOut, tags=["settings"])
def get_app_settings(settings: SettingsDep, _user: UserDep) -> SettingsOut:
    return SettingsOut(
        version=__version__,
        environment=settings.env,
        auth_required=settings.auth_required,
        retention_days=settings.retention_days,
        max_upload_mb=settings.max_upload_bytes // (1024 * 1024),
        max_rows=settings.max_rows,
        max_cols=settings.max_cols,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        native_accelerator=accel.native_available(),
        synthetic_demo_available=True,
    )


@router.post("/admin/retention/purge", response_model=PurgeOut, tags=["settings"], summary="Delete datasets past their retention deadline")
def purge(db: SessionDep, settings: SettingsDep, admin: AdminDep) -> PurgeOut:
    return PurgeOut(datasets_deleted=purge_expired(db, settings, actor=admin.name))
