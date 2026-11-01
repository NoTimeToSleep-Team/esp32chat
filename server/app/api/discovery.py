from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import ClientKind
from app.services.auth import AuthError, AuthService
from app.services.module_registry import ModuleRegistryService


router = APIRouter(tags=["discovery"])


def _registry_service(request: Request) -> ModuleRegistryService:
    data_layer = request.app.state.data_layer
    return ModuleRegistryService(db_path=data_layer.database_path)


@router.get("/api/capabilities")
async def capabilities(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    auth = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        auth.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    service = _registry_service(request)
    return {
        "status": "ok",
        "capabilities": service.compute_capability_map(),
    }
