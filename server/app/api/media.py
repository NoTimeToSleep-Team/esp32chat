from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.models import ClientKind, MediaAttachment, UserRole
from app.services.auth import AuthError, AuthService
from app.services.media import MAX_UPLOAD_BYTES, MediaError, MediaService


router = APIRouter(prefix="/media/api", tags=["media"])


class UploadResponse(BaseModel):
    status: str
    attachment: dict[str, object]


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _media_service(request: Request) -> MediaService:
    data_layer = request.app.state.data_layer
    return MediaService(db_path=data_layer.database_path, storage_root=data_layer.storage_root)


def _resolve_user_id(request: Request, session_token: str) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    if session.user.user_id is None:
        raise HTTPException(status_code=500, detail={"code": "invalid_user", "message": "Authenticated user id is missing"})
    return session.user.user_id


def _attachment_payload(attachment: MediaAttachment) -> dict[str, object]:
    return {
        "attachment_id": attachment.attachment_id,
        "owner_user_id": attachment.owner_user_id,
        "filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "media_kind": attachment.media_kind.value,
        "size_bytes": attachment.size_bytes,
        "sha256_hex": attachment.sha256_hex,
        "created_at_ms": attachment.created_at_ms,
        "download_url": f"/media/api/attachments/{attachment.attachment_id}/download",
    }


def _raise_media_error(exc: MediaError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post("/attachments")
async def upload_attachment(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    file: UploadFile = File(...),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    service = _media_service(request)
    try:
        attachment = service.create_attachment(
            owner_user_id=user_id,
            original_filename=file.filename,
            mime_type=file.content_type,
            content=content,
        )
    except MediaError as exc:
        _raise_media_error(exc)
    return {"status": "ok", "attachment": _attachment_payload(attachment)}


@router.get("/attachments")
async def list_my_attachments(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=100, ge=1, le=300),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _media_service(request)
    try:
        items = service.list_owned_attachments(owner_user_id=user_id, limit=limit)
    except MediaError as exc:
        _raise_media_error(exc)
    return {"status": "ok", "count": len(items), "items": [_attachment_payload(item) for item in items]}


@router.get("/stats")
async def media_storage_stats(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    if session.user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Admin or moderator required"},
        )
    return {"status": "ok", **_media_service(request).storage_stats()}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    request: Request,
    attachment_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> FileResponse:
    user_id = _resolve_user_id(request, session_token)
    service = _media_service(request)
    try:
        download = service.resolve_download(attachment_id=attachment_id, requester_user_id=user_id)
    except MediaError as exc:
        _raise_media_error(exc)
    return FileResponse(
        path=download.absolute_path,
        media_type=download.attachment.mime_type,
        filename=download.attachment.original_filename,
    )
