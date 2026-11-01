# DEPRECATED RPi-Only: требует внутренние контроллеры, не активно в RPi-only архитектуре.
from __future__ import annotations

import os
import sqlite3
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, ModuleInfo, ModuleKind, UserRole
from app.services.auth import AuthError, AuthService
from app.services.edge_nodes import EdgeNodeDeployment, EdgeNodeError, EdgeNodeService
from app.services.module_registry import ModuleRegistryService


router = APIRouter(tags=["deployment", "m5tab"])


class StartDeploymentRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    module_id: str = Field(min_length=1, max_length=128)
    ssid: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)
    profile_options: dict[str, Any] = Field(default_factory=dict)


class StopDeploymentRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    deployment_id: int = Field(ge=1)


def _db_path(request: Request) -> str:
    return request.app.state.data_layer.database_path


def _auth_service(request: Request) -> AuthService:
    return AuthService(db_path=_db_path(request))


def _edge_service(request: Request) -> EdgeNodeService:
    return EdgeNodeService(db_path=_db_path(request))


def _registry_service(request: Request) -> ModuleRegistryService:
    return ModuleRegistryService(db_path=_db_path(request))


def _resolve_admin_user_id(request: Request, session_token: str) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    if session.user.role != UserRole.ADMIN or not session.user.can_access_admin_features():
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_only", "message": "Admin role is required"},
        )
    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Admin user id is missing"},
        )
    return session.user.user_id


def _raise_edge_error(exc: EdgeNodeError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _deployment_payload(deployment: EdgeNodeDeployment) -> dict[str, object]:
    return {
        "deployment_id": deployment.deployment_id,
        "module_id": deployment.module_id,
        "network_ssid": deployment.network_ssid,
        "network_ssid_storage": "obfuscated_placeholder_not_plaintext",
        "network_password_configured": bool(deployment.network_password_hash),
        "status": deployment.status,
        "local_profile": deployment.local_profile,
        "local_ip": deployment.local_ip,
        "mDNS_name": deployment.mdns_name,
        "created_at_ms": deployment.created_at_ms,
        "updated_at_ms": deployment.updated_at_ms,
        "deployed_by_admin_user_id": deployment.deployed_by_admin_user_id,
    }


def _module_payload(module: ModuleInfo) -> dict[str, object]:
    return {
        "id": module.id,
        "slug": module.slug,
        "display_name": module.display_name,
        "kind": module.kind.value,
        "status": module.status.value,
        "feature_flags": module.feature_flags,
    }


@router.post("/admin/api/deployment/start")
async def start_deployment(request: Request, payload: StartDeploymentRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _edge_service(request)
    try:
        deployment_id = service.deploy_node(
            admin_user_id=admin_user_id,
            module_id=payload.module_id,
            ssid=payload.ssid,
            password=payload.password,
            profile_options=payload.profile_options,
        )
        deployment = service.get_deployment(deployment_id)
    except EdgeNodeError as exc:
        _raise_edge_error(exc)

    return {"status": "ok", "deployment_id": deployment_id, "deployment": _deployment_payload(deployment)}


@router.post("/admin/api/deployment/stop")
async def stop_deployment(request: Request, payload: StopDeploymentRequest) -> dict[str, object]:
    _resolve_admin_user_id(request, payload.session_token)
    try:
        deployment = _edge_service(request).stop_node(payload.deployment_id)
    except EdgeNodeError as exc:
        _raise_edge_error(exc)
    return {"status": "ok", "deployment": _deployment_payload(deployment)}


@router.get("/admin/api/deployment/status")
async def deployment_status(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    deployments = _edge_service(request).list_deployments()
    return {
        "status": "ok",
        "count": len(deployments),
        "items": [_deployment_payload(item) for item in deployments],
    }


@router.get("/api/m5tab/info")
async def m5tab_info(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    modules = _registry_service(request).load_registry()
    capability_map = _registry_service(request).compute_capability_map()
    uptime_seconds = int(monotonic() - getattr(request.app.state, "started_at_monotonic", monotonic()))
    return {
        "status": "ok",
        "user_count": _count_users(_db_path(request)),
        "system_load": {"status": "placeholder", "hardware_io": False},
        "ram_used": _ram_used_placeholder(),
        "uptime_seconds": uptime_seconds,
        "module_status": [_module_payload(module) for module in modules],
        "edge_node_limit": int(capability_map.get("edge_node_limit", 0)),
    }


@router.get("/api/m5tab/admin")
async def m5tab_admin(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    db_path = _db_path(request)
    return {
        "status": "ok",
        "user_list_summary": _user_list_summary(db_path),
        "recent_support_tickets": _recent_support_tickets(db_path),
        "blog_drafts_count": _blog_drafts_count(db_path),
    }


@router.get("/api/m5tab/deployment")
async def m5tab_deployment(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    modules = _registry_service(request).load_registry()
    deployments = _edge_service(request).list_deployments()
    available_modules = [
        _module_payload(module)
        for module in modules
        if module.kind in {ModuleKind.M5STAMP_S3, ModuleKind.ESP32_S3}
    ]
    return {
        "status": "ok",
        "available_modules": available_modules,
        "edge_deployment_status": [_deployment_payload(item) for item in deployments],
    }


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _count_users(db_path: str) -> int:
    with _connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        return int(row["total"] if row is not None else 0)


def _ram_used_placeholder() -> dict[str, object]:
    return {
        "status": "placeholder",
        "process_rss_bytes": None,
        "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
    }


def _user_list_summary(db_path: str) -> dict[str, object]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT role, status, COUNT(*) AS total FROM users GROUP BY role, status",
        ).fetchall()
        recent = connection.execute(
            "SELECT id, login, role, status, created_at_ms FROM users ORDER BY created_at_ms DESC, id DESC LIMIT 20",
        ).fetchall()
    return {
        "counts": [dict(row) for row in rows],
        "recent_users": [dict(row) for row in recent],
    }


def _recent_support_tickets(db_path: str) -> list[dict[str, object]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, title, status, updated_at_ms, last_message_at_ms
            FROM support_tickets
            ORDER BY updated_at_ms DESC, id DESC
            LIMIT 10
            """,
        ).fetchall()
    return [dict(row) for row in rows]


def _blog_drafts_count(db_path: str) -> int:
    with _connect(db_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'blog_drafts'",
        ).fetchone()
        if table is None:
            return 0
        row = connection.execute("SELECT COUNT(*) AS total FROM blog_drafts").fetchone()
        return int(row["total"] if row is not None else 0)
