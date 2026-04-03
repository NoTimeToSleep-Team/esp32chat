from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import ClientKind
from app.security import BruteForceGuard, SecurityAuditService
from app.services.auth import AuthError, AuthResult, AuthService
from app.services.registration import RegistrationError, RegistrationService


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)
    client_kind: ClientKind = ClientKind.WEB


class LogoutRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


class RegisterRequest(BaseModel):
    login: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=512)
    phone: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=256)
    client_kind: ClientKind = ClientKind.WEB


class GuestRequest(BaseModel):
    client_kind: ClientKind = ClientKind.WEB


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _registration_service(request: Request) -> RegistrationService:
    data_layer = request.app.state.data_layer
    return RegistrationService(db_path=data_layer.database_path)


def _bruteforce_guard(request: Request) -> BruteForceGuard:
    data_layer = request.app.state.data_layer
    settings = request.app.state.settings
    return BruteForceGuard(
        db_path=data_layer.database_path,
        window_ms=settings.bruteforce_window_ms,
        login_attempt_limit=settings.bruteforce_login_attempt_limit,
        ip_attempt_limit=settings.bruteforce_ip_attempt_limit,
        block_ms=settings.bruteforce_block_ms,
    )


def _security_audit(request: Request) -> SecurityAuditService:
    return request.app.state.security_audit


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    client = request.client
    if client and client.host:
        return client.host
    return "unknown"


def _auth_result_payload(result: AuthResult) -> dict[str, object]:
    return {
        "status": "ok",
        "access_mode": result.access_mode.value,
        "user": {
            "id": result.user.user_id,
            "login": result.user.login,
            "role": result.user.role.value,
            "status": result.user.status.value,
        },
        "session": {
            "token": result.session.token,
            "created_at_ms": result.session.created_at_ms,
            "expires_at_ms": result.session.expires_at_ms,
        },
    }


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, object]:
    service = _auth_service(request)
    guard = _bruteforce_guard(request)
    audit = _security_audit(request)
    ip_address = _client_ip(request)
    normalized_login = payload.login.strip()

    decision = guard.check_allowed(ip_address=ip_address)
    if not decision.allowed:
        audit.log_event(
            "security.login_blocked",
            actor_kind="ip",
            actor_id=ip_address,
            details={
                "login": normalized_login,
                "blocked_until_ms": decision.blocked_until_ms,
                "reason": "ip_blocked",
            },
        )
        raise HTTPException(
            status_code=429,
            detail={
                "code": "bruteforce_block",
                "message": "Too many failed login attempts, try later",
                "blocked_until_ms": decision.blocked_until_ms,
            },
        )

    try:
        result = service.login(
            login=normalized_login,
            password=payload.password,
            client_kind=payload.client_kind,
        )
    except AuthError as exc:
        blocked_until_ms: int | None = None
        if exc.code == "invalid_credentials":
            blocked_until_ms = guard.record_attempt(
                login=normalized_login,
                ip_address=ip_address,
                success=False,
            )

        audit.log_event(
            "security.login_failed",
            actor_kind="ip",
            actor_id=ip_address,
            details={
                "login": normalized_login,
                "code": exc.code,
                "status_code": exc.status_code,
                "blocked_until_ms": blocked_until_ms,
                "client_kind": payload.client_kind.value,
            },
        )

        if blocked_until_ms is not None:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "bruteforce_block",
                    "message": "Too many failed login attempts, try later",
                    "blocked_until_ms": blocked_until_ms,
                },
            ) from exc

        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    guard.record_attempt(
        login=normalized_login,
        ip_address=ip_address,
        success=True,
    )
    audit.log_event(
        "security.login_success",
        actor_kind="user",
        actor_id=str(result.user.user_id) if result.user.user_id is not None else None,
        details={
            "login": result.user.login,
            "ip_address": ip_address,
            "client_kind": payload.client_kind.value,
        },
    )

    return _auth_result_payload(result)


@router.post("/register")
async def register(payload: RegisterRequest, request: Request) -> dict[str, object]:
    service = _registration_service(request)
    try:
        result = service.register_user(
            login=payload.login,
            password=payload.password,
            phone=payload.phone,
            device_id=payload.device_id,
            client_kind=payload.client_kind,
        )
    except RegistrationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return _auth_result_payload(result)


@router.post("/guest")
async def guest_login(payload: GuestRequest, request: Request) -> dict[str, object]:
    service = _registration_service(request)
    try:
        result = service.create_guest_session(client_kind=payload.client_kind)
    except RegistrationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return _auth_result_payload(result)


@router.post("/logout")
async def logout(payload: LogoutRequest, request: Request) -> dict[str, object]:
    service = _auth_service(request)
    revoked = service.logout(payload.session_token)
    return {
        "status": "ok",
        "revoked": revoked,
    }


@router.get("/session/{session_token}")
async def get_session(
    session_token: str,
    request: Request,
    client_kind: ClientKind = ClientKind.WEB,
) -> dict[str, object]:
    service = _auth_service(request)
    try:
        result = service.get_session(session_token, client_kind=client_kind)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return _auth_result_payload(result)
