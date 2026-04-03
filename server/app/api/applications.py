from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import (
    ApplicationDraft,
    ApplicationRecord,
    ApplicationStatus,
    ClientKind,
    UserRole,
)
from app.services.applications import ApplicationError, ApplicationService
from app.services.auth import AuthError, AuthService


router = APIRouter(prefix="/applications", tags=["applications"])


class CreateApplicationRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=256)
    class_group: str = Field(min_length=1, max_length=64)
    is_school_member: bool


class UpdateApplicationStatusRequest(BaseModel):
    status: ApplicationStatus
    review_note: str | None = Field(default=None, max_length=2048)


def _application_service(request: Request) -> ApplicationService:
    data_layer = request.app.state.data_layer
    return ApplicationService(db_path=data_layer.database_path)


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _require_admin_user_id(request: Request, session_token: str) -> int:
    auth = _auth_service(request)
    try:
        result = auth.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    if result.user.role != UserRole.ADMIN or not result.user.can_access_admin_features():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "admin_only",
                "message": "Admin role is required",
            },
        )

    if result.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "invalid_user",
                "message": "Admin user id is missing",
            },
        )

    return result.user.user_id


def _record_to_payload(record: ApplicationRecord) -> dict[str, object]:
    return {
        "application_id": record.application_id,
        "first_name": record.first_name,
        "last_name": record.last_name,
        "phone": record.phone,
        "email": record.email,
        "class_group": record.class_group,
        "is_school_member": record.is_school_member,
        "status": record.status.value,
        "review_note": record.review_note,
        "reviewed_by_user_id": record.reviewed_by_user_id,
        "created_at_ms": record.created_at_ms,
        "updated_at_ms": record.updated_at_ms,
    }


@router.post("")
async def create_application(
    payload: CreateApplicationRequest,
    request: Request,
) -> dict[str, object]:
    service = _application_service(request)
    try:
        record = service.submit(
            ApplicationDraft(
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone=payload.phone,
                email=payload.email,
                class_group=payload.class_group,
                is_school_member=payload.is_school_member,
            )
        )
    except (ApplicationError, ValueError) as exc:
        if isinstance(exc, ApplicationError):
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
                "code": "invalid_application_payload",
                "message": str(exc),
            },
        )

    return {
        "status": "ok",
        "application": _record_to_payload(record),
    }


@router.get("")
async def list_applications(
    request: Request,
    x_session_token: str = Header(..., alias="X-Session-Token"),
    status: ApplicationStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    _require_admin_user_id(request, x_session_token)

    service = _application_service(request)
    records = service.list_queue(status=status, limit=limit, offset=offset)
    return {
        "status": "ok",
        "count": len(records),
        "items": [_record_to_payload(record) for record in records],
    }


@router.post("/{application_id}/status")
async def update_application_status(
    application_id: int,
    payload: UpdateApplicationStatusRequest,
    request: Request,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> dict[str, object]:
    admin_user_id = _require_admin_user_id(request, x_session_token)

    service = _application_service(request)
    try:
        updated = service.set_status(
            application_id=application_id,
            new_status=payload.status,
            reviewed_by_user_id=admin_user_id,
            review_note=payload.review_note,
        )
    except ApplicationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "application": _record_to_payload(updated),
    }
