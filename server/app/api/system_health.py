from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import ClientKind, UserRole
from app.services.auth import AuthError, AuthService
from app.services.system_health import SystemHealthService

router = APIRouter(tags=["ops"])


def _require_admin(request: Request, session_token: str) -> None:
    service = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail={"code": "admin_only", "message": "Admin role is required"})


@router.get("/ops/system-health", summary="Get RPi system health snapshot")
async def get_system_health(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
):
    _require_admin(request, session_token)
    settings = request.app.state.settings
    dl = request.app.state.data_layer
    service = SystemHealthService(
        db_path=dl.database_path,
        storage_root=settings.storage_root,
        server_version="1.0.0",
    )
    snap = service.get_snapshot()
    return {
        "cpu_percent": snap.cpu_percent,
        "memory_percent": snap.memory_percent,
        "memory_available_mb": snap.memory_available_mb,
        "disk_usage_percent": snap.disk_usage_percent,
        "disk_free_mb": snap.disk_free_mb,
        "uptime_seconds": snap.uptime_seconds,
        "uptime_days": round(snap.uptime_seconds / 86400, 2),
        "python_version": snap.python_version,
        "server_version": snap.server_version,
        "db_size_mb": snap.db_size_mb,
        "storage_free_mb": snap.storage_free_mb,
    }
