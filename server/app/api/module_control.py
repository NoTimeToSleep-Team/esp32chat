# DEPRECATED RPi-Only: требует внутренние контроллеры, не активно в RPi-only архитектуре.
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, ModuleInfo, UserRole
from app.services.auth import AuthError, AuthService
from app.services.module_registry import ModuleRegistryService


router = APIRouter(tags=["module-control"])


class ModuleControlRequest(BaseModel):
    module_slug: str = Field(min_length=1, max_length=128)
    session_token: str = Field(min_length=8, max_length=512)


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _registry_service(request: Request) -> ModuleRegistryService:
    data_layer = request.app.state.data_layer
    return ModuleRegistryService(db_path=data_layer.database_path)


def _require_admin(request: Request, session_token: str) -> None:
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


def _module_payload(module: ModuleInfo) -> dict[str, object]:
    return {
        "id": module.id,
        "slug": module.slug,
        "display_name": module.display_name,
        "kind": module.kind.value,
        "transport": module.transport.value,
        "criticality": module.criticality.value,
        "status": module.status.value,
        "last_heartbeat_ms": module.last_heartbeat_ms,
        "feature_flags": module.feature_flags,
        "notes": module.notes,
    }


@router.get("/admin/api/modules")
def list_modules(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _require_admin(request, session_token)
    service = _registry_service(request)
    modules = service.load_registry()
    return {
        "status": "ok",
        "count": len(modules),
        "items": [_module_payload(module) for module in modules],
    }


@router.post("/admin/api/modules/enable")
def enable_module(request: Request, payload: ModuleControlRequest) -> dict[str, object]:
    _require_admin(request, payload.session_token)
    service = _registry_service(request)
    try:
        module = service.set_module_enabled(payload.module_slug, enabled=True)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "module_not_found", "message": "Module not found"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_module_slug", "message": str(exc)},
        ) from exc

    if module.slug == "pn532" and hasattr(request.app.state, "enable_rfid_router"):
        request.app.state.enable_rfid_router()

    return {"status": "ok", "module": _module_payload(module)}


@router.post("/admin/api/modules/disable")
def disable_module(request: Request, payload: ModuleControlRequest) -> dict[str, object]:
    _require_admin(request, payload.session_token)
    service = _registry_service(request)
    try:
        module = service.set_module_enabled(payload.module_slug, enabled=False)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "module_not_found", "message": "Module not found"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_module_slug", "message": str(exc)},
        ) from exc

    return {"status": "ok", "module": _module_payload(module)}
