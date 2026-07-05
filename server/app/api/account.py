from __future__ import annotations

import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.models import AccountLimits, AccountProfile, AccountProfileUpdate, AvatarImage, ClientKind
from app.services.account import AccountError, AccountService
from app.services.auth import AuthError, AuthService


router = APIRouter(tags=["account"])


class UpdateAccountProfileRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    display_name: str | None = Field(default=None, max_length=128)
    profile_bio: str | None = Field(default=None, max_length=1024)


class UpdateAccountAvatarRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    image_base64: str = Field(min_length=16, max_length=6_000_000)
    image_mime_type: str | None = Field(default=None, max_length=32)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "account" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _account_service(request: Request) -> AccountService:
    data_layer = request.app.state.data_layer
    avatars_root = Path(data_layer.storage_root) / "avatars"
    return AccountService(
        db_path=data_layer.database_path,
        avatars_root=avatars_root,
    )


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


def _profile_payload(profile: AccountProfile) -> dict[str, object]:
    return {
        "user_id": profile.user_id,
        "login": profile.login,
        "role": profile.role.value,
        "status": profile.status.value,
        "phone": profile.phone,
        "display_name": profile.display_name,
        "profile_bio": profile.profile_bio,
        "avatar_url": None,
        "avatar_updated_at_ms": profile.avatar_updated_at_ms,
    }


def _limits_payload(limits: AccountLimits) -> dict[str, object]:
    return {
        "role": limits.role.value,
        "max_custom_chats": limits.max_custom_chats,
        "current_custom_chats": limits.current_custom_chats,
        "remaining_custom_chats": limits.remaining_custom_chats,
        "can_create_custom_chats": limits.can_create_custom_chats,
    }


def _decode_avatar_payload(
    *,
    image_base64: str,
    image_mime_type: str | None,
) -> AvatarImage:
    raw = image_base64.strip()
    mime_from_data_url: str | None = None

    if raw.startswith("data:") and "," in raw:
        header, payload = raw.split(",", 1)
        if ";base64" not in header:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_avatar_payload",
                    "message": "Avatar data URL must be base64-encoded",
                },
            )
        mime_from_data_url = header[5:].split(";", 1)[0].strip().lower()
        raw = payload

    raw = "".join(raw.split())
    mime = (mime_from_data_url or (image_mime_type or "")).strip().lower()

    if not mime:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_avatar_payload",
                "message": "Avatar mime type is required",
            },
        )

    try:
        content = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_avatar_payload",
                "message": "Avatar base64 payload is invalid",
            },
        ) from exc

    try:
        return AvatarImage(content=content, mime_type=mime)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_avatar_payload",
                "message": str(exc),
            },
        ) from exc


@router.get("/account", response_class=HTMLResponse)
async def account_page() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/account/api/profile")
async def get_account_profile(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _account_service(request)

    try:
        profile = service.get_profile(user_id=user_id)
    except AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    payload = _profile_payload(profile)
    payload["avatar_url"] = (
        f"/account/api/profile/avatar?session_token={session_token}"
        if profile.avatar_path
        else None
    )
    return {
        "status": "ok",
        "profile": payload,
    }


@router.post("/account/api/profile")
async def update_account_profile(
    request: Request,
    payload: UpdateAccountProfileRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _account_service(request)

    try:
        profile = service.update_profile(
            user_id=user_id,
            draft=AccountProfileUpdate(
                display_name=payload.display_name,
                profile_bio=payload.profile_bio,
            ),
        )
    except (AccountError, ValueError) as exc:
        if isinstance(exc, AccountError):
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
                "code": "invalid_profile_payload",
                "message": str(exc),
            },
        )

    data = _profile_payload(profile)
    data["avatar_url"] = (
        f"/account/api/profile/avatar?session_token={payload.session_token}"
        if profile.avatar_path
        else None
    )
    return {
        "status": "ok",
        "profile": data,
    }


@router.post("/account/api/avatar")
async def update_account_avatar(
    request: Request,
    payload: UpdateAccountAvatarRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _account_service(request)

    avatar = _decode_avatar_payload(
        image_base64=payload.image_base64,
        image_mime_type=payload.image_mime_type,
    )

    try:
        profile = service.set_avatar(user_id=user_id, avatar=avatar)
    except AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    data = _profile_payload(profile)
    data["avatar_url"] = (
        f"/account/api/profile/avatar?session_token={payload.session_token}&v={profile.avatar_updated_at_ms or 0}"
        if profile.avatar_path
        else None
    )
    return {
        "status": "ok",
        "profile": data,
    }


@router.get("/account/api/profile/avatar")
async def get_account_avatar(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> FileResponse:
    user_id = _resolve_user_id(request, session_token)
    service = _account_service(request)

    try:
        file_path, mime_type = service.get_avatar_file(user_id=user_id)
    except AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return FileResponse(path=str(file_path), media_type=mime_type)


@router.get("/account/api/limits")
async def get_account_limits(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _account_service(request)

    try:
        limits = service.get_limits(user_id=user_id)
    except AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "limits": _limits_payload(limits),
    }
