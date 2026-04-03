from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter, Request


router = APIRouter(tags=["health"])


def _uptime_ms(request: Request) -> int:
    started_at = getattr(request.app.state, "started_at_monotonic", None)
    if started_at is None:
        return 0
    return int((monotonic() - started_at) * 1000)


def _read_runtime_state(request: Request) -> dict[str, object]:
    data_layer = getattr(request.app.state, "data_layer", None)
    if data_layer is None:
        return {"degraded_mode": False, "reason": None, "updated_at_ms": 0}

    connection = sqlite3.connect(str(data_layer.database_path))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT degraded_mode, reason, updated_at_ms
            FROM ops_runtime_state
            WHERE id = 1
            """,
        ).fetchone()
        if row is None:
            return {"degraded_mode": False, "reason": None, "updated_at_ms": 0}
        return {
            "degraded_mode": bool(int(row["degraded_mode"])),
            "reason": str(row["reason"]) if row["reason"] is not None else None,
            "updated_at_ms": int(row["updated_at_ms"]),
        }
    except sqlite3.OperationalError:
        return {"degraded_mode": False, "reason": None, "updated_at_ms": 0}
    finally:
        connection.close()


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    runtime_state = _read_runtime_state(request)
    return {
        "status": "ok",
        "service": "local-chat-server",
        "profile": settings.profile,
        "timestamp_ms": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        "uptime_ms": _uptime_ms(request),
        "runtime": runtime_state,
    }


@router.get("/health/ready")
async def readiness(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    data_layer = getattr(request.app.state, "data_layer", None)
    runtime_state = _read_runtime_state(request)
    return {
        "status": "ready",
        "service": "local-chat-server",
        "profile": settings.profile,
        "checks": {
            "config_loaded": True,
            "data_layer_initialized": data_layer is not None,
        },
        "data_layer": {
            "database_path": str(data_layer.database_path) if data_layer else None,
            "applied_migrations": len(data_layer.applied_migrations) if data_layer else 0,
        },
        "runtime": runtime_state,
        "uptime_ms": _uptime_ms(request),
    }
