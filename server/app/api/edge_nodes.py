# DEPRECATED RPi-Only: требует внутренние контроллеры, не активно в RPi-only архитектуре.
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import ClientKind, ModuleInfo, ModuleKind, ModuleStatus, UserRole
from app.services.auth import AuthError, AuthService
from app.services.edge_nodes import EdgeNodeService
from app.services.module_registry import ModuleRegistryService


router = APIRouter(tags=["edge-nodes"])


def _registry_service(request: Request) -> ModuleRegistryService:
    return ModuleRegistryService(db_path=request.app.state.data_layer.database_path)


def _edge_service(request: Request) -> EdgeNodeService:
    return EdgeNodeService(db_path=request.app.state.data_layer.database_path)


def _edge_module_payload(module: ModuleInfo) -> dict[str, object]:
    return {
        "id": module.id,
        "slug": module.slug,
        "display_name": module.display_name,
        "kind": module.kind.value,
        "status": module.status.value,
        "last_heartbeat_ms": module.last_heartbeat_ms,
    }


@router.get("/devices/api/edge/capabilities")
async def edge_capabilities(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    service = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail={"code": "admin_only", "message": "Admin role is required"})
    registry = _registry_service(request)
    modules = registry.load_registry()
    usable_statuses = {ModuleStatus.DETECTED, ModuleStatus.DEGRADED, ModuleStatus.OK}
    detected_stamps = [
        module
        for module in modules
        if module.kind == ModuleKind.M5STAMP_S3 and module.status in usable_statuses
    ]
    detected_esp32s = [
        module
        for module in modules
        if module.kind == ModuleKind.ESP32_S3 and module.status in usable_statuses
    ]
    return {
        "status": "ok",
        "max_edge_nodes": registry.recompute_edge_node_limit(modules),
        "detected_stamps": [_edge_module_payload(module) for module in detected_stamps],
        "detected_esp32s": [_edge_module_payload(module) for module in detected_esp32s],
        "active_deployments": _edge_service(request).active_deployment_count(),
    }
