from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import DeviceOwnership, DeviceProfileDraft, DeviceProfileView, ClientKind
from app.services.auth import AuthError, AuthService
from app.services.devices import DeviceCatalogError, DeviceCatalogService


router = APIRouter(tags=["devices"])


class PublishDeviceProfileRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    slug: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    short_description: str = Field(min_length=1, max_length=512)
    firmware_archive_url: str | None = Field(default=None, max_length=2048)
    install_guide: str = Field(min_length=1, max_length=16000)
    pairing_guide: str = Field(min_length=1, max_length=16000)
    combo_reset_guide: str = Field(min_length=1, max_length=16000)
    is_published: bool = True


class SetDeviceOwnershipRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    has_device: bool = True


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "devices" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _device_service(request: Request) -> DeviceCatalogService:
    data_layer = request.app.state.data_layer
    return DeviceCatalogService(db_path=data_layer.database_path)


def _resolve_user_id(request: Request, session_token: str) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "invalid_user",
                "message": "Authenticated user id is missing",
            },
        )

    return session.user.user_id


def _device_payload(view: DeviceProfileView) -> dict[str, object]:
    profile = view.profile
    return {
        "device_id": profile.device_id,
        "slug": profile.slug,
        "title": profile.title,
        "short_description": profile.short_description,
        "firmware_archive_url": profile.firmware_archive_url,
        "install_guide": profile.install_guide,
        "pairing_guide": profile.pairing_guide,
        "combo_reset_guide": profile.combo_reset_guide,
        "is_published": profile.is_published,
        "created_by_user_id": profile.created_by_user_id,
        "created_at_ms": profile.created_at_ms,
        "updated_at_ms": profile.updated_at_ms,
        "published_at_ms": profile.published_at_ms,
        "has_device": view.has_device,
    }


def _ownership_payload(ownership: DeviceOwnership) -> dict[str, object]:
    return {
        "user_id": ownership.user_id,
        "device_id": ownership.device_id,
        "has_device": ownership.has_device,
        "updated_at_ms": ownership.updated_at_ms,
    }


@router.get("/devices", response_class=HTMLResponse)
async def devices_page() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/devices/api/catalog")
async def list_devices_catalog(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _device_service(request)

    try:
        items = service.list_profiles(
            requester_user_id=user_id,
            limit=limit,
            offset=offset,
        )
    except DeviceCatalogError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "count": len(items),
        "items": [_device_payload(item) for item in items],
    }


@router.get("/devices/api/catalog/{device_id}")
async def get_device_profile(
    request: Request,
    device_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _device_service(request)

    try:
        item = service.get_profile(
            requester_user_id=user_id,
            device_id=device_id,
        )
    except DeviceCatalogError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "device": _device_payload(item),
    }


@router.post("/devices/api/catalog")
async def publish_device_profile(
    request: Request,
    payload: PublishDeviceProfileRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _device_service(request)

    try:
        profile = service.publish_profile(
            actor_user_id=user_id,
            draft=DeviceProfileDraft(
                slug=payload.slug,
                title=payload.title,
                short_description=payload.short_description,
                firmware_archive_url=payload.firmware_archive_url,
                install_guide=payload.install_guide,
                pairing_guide=payload.pairing_guide,
                combo_reset_guide=payload.combo_reset_guide,
            ),
            is_published=payload.is_published,
        )
    except (DeviceCatalogError, ValueError) as exc:
        if isinstance(exc, DeviceCatalogError):
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "code": exc.code,
                    "message": exc.message,
                },
            ) from exc
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_device_payload",
                "message": str(exc),
            },
        )

    return {
        "status": "ok",
        "device": _device_payload(DeviceProfileView(profile=profile, has_device=False)),
    }


@router.post("/devices/api/catalog/{device_id}/ownership")
async def set_device_ownership(
    request: Request,
    device_id: int,
    payload: SetDeviceOwnershipRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _device_service(request)

    try:
        ownership = service.set_ownership(
            requester_user_id=user_id,
            device_id=device_id,
            has_device=payload.has_device,
        )
    except DeviceCatalogError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "ownership": _ownership_payload(ownership),
    }
