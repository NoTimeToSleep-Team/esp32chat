from __future__ import annotations

import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.models import AccountLimits, AccountProfile, AccountProfileUpdate, AvatarImage, ClientKind, UserRole
from app.services.account import AccountError, AccountService
from app.services.auth import AuthError, AuthService


router = APIRouter(tags=["account"])


class UpdateAccountProfileRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    display_name: str | None = Field(default=None, max_length=128)
    avatar_emoji: str | None = Field(default=None, max_length=8)
    profile_bio: str | None = Field(default=None, max_length=1024)


class UpdateAccountAvatarRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    image_base64: str = Field(min_length=16, max_length=6_000_000)
    image_mime_type: str | None = Field(default=None, max_length=32)


class ClearAccountAvatarRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


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
        "avatar_emoji": getattr(profile, "avatar_emoji", None),
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



@router.get("/account/api/profile/{user_id:int}")
async def get_user_profile(
    request: Request,
    user_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    """Get any user's public profile (read-only, no edit permissions)."""
    auth_service = _auth_service(request)
    try:
        session = auth_service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.user_id is None:
        raise HTTPException(status_code=500, detail={"code": "invalid_user", "message": "Authenticated user id is missing"})
    service = _account_service(request)
    try:
        profile = service.get_profile(user_id=user_id)
    except AccountError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    data = _profile_payload(profile)
    can_see_private = (
        profile.user_id == session.user.user_id
        or session.user.role in {UserRole.ADMIN, UserRole.MODERATOR}
    )
    if not can_see_private:
        data["phone"] = None
    data["avatar_url"] = (
        f"/account/api/profile/avatar?session_token={session_token}&user_id={profile.user_id}&v={profile.avatar_updated_at_ms or 0}"
        if profile.avatar_path else None
    )
    return {"status": "ok", "profile": data}


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
                avatar_emoji=payload.avatar_emoji,
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


@router.post("/account/api/avatar/remove")
async def remove_account_avatar(
    request: Request,
    payload: ClearAccountAvatarRequest,
) -> dict[str, object]:
    """Drop the uploaded photo avatar so the emoji avatar is used again."""
    user_id = _resolve_user_id(request, payload.session_token)
    service = _account_service(request)

    try:
        profile = service.clear_avatar(user_id=user_id)
    except AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    data = _profile_payload(profile)
    data["avatar_url"] = None
    return {
        "status": "ok",
        "profile": data,
    }


@router.get("/account/api/profile/avatar")
async def get_account_avatar(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    user_id: int | None = Query(default=None),
) -> FileResponse:
    target_user_id = user_id if user_id is not None else _resolve_user_id(request, session_token)
    service = _account_service(request)

    try:
        file_path, mime_type = service.get_avatar_file(user_id=target_user_id)
    except AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return FileResponse(path=str(file_path), media_type=mime_type)


@router.get("/account/api/me/internet")
async def get_my_internet_status(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    import sqlite3
    conn = sqlite3.connect(request.app.state.data_layer.database_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT enabled, granted_at_ms FROM internet_access WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    enabled = bool(row["enabled"]) if row else False
    granted_at_ms = row["granted_at_ms"] if row else 0
    return {"status": "ok", "internet_enabled": enabled, "granted_at_ms": granted_at_ms}


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
