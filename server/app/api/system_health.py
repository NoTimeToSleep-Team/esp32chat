from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.system_health import SystemHealthService

router = APIRouter(tags=["ops"])


@router.get("/ops/system-health", summary="Get RPi system health snapshot")
async def get_system_health(request: Request):
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
