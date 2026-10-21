from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import ClientKind
from app.security import BruteForceGuard, SecurityAuditService
from app.services.activity_log import ActivityLogService
from app.services.auth import AuthError, AuthResult, AuthService
from app.services.chat import ChatService
from app.services.device_pairing import DevicePairingError, DevicePairingService
from app.services.registration import RegistrationError, RegistrationService


router = APIRouter(prefix="/auth", tags=["auth"])


def _activity_log(request: Request) -> ActivityLogService:
    return ActivityLogService(db_path=request.app.state.data_layer.database_path)


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)
    client_kind: ClientKind = ClientKind.WEB
    device_id: str | None = Field(default=None, max_length=256)


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
                ip_address=ip_address,
                device_id=payload.device_id,
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

    _activity_log(request).log("login", user_id=result.user.user_id, user_login=result.user.login, details=f"ip={ip_address}")
    return _auth_result_payload(result)


class DeviceChallengeRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=256)


class DeviceSessionRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=256)
    challenge: str | None = Field(default=None, max_length=128)
    proof: str | None = Field(default=None, max_length=128)


def _device_pairing_service(request: Request) -> DevicePairingService:
    data_layer = request.app.state.data_layer
    return DevicePairingService(db_path=data_layer.database_path)


@router.post("/device-challenge")
async def device_challenge(request: Request, payload: DeviceChallengeRequest) -> dict[str, object]:
    service = _device_pairing_service(request)
    try:
        challenge, expires_in_ms = service.issue_challenge(payload.device_id)
    except DevicePairingError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return {
        "status": "ok",
        "challenge": challenge,
        "expires_in_ms": expires_in_ms,
    }


@router.post("/device-session")
async def device_session(request: Request, payload: DeviceSessionRequest) -> dict[str, object]:
    if not payload.challenge or not payload.proof:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "device_proof_required",
                "message": "Device challenge and proof are required",
            },
        )

    pairing_service = _device_pairing_service(request)
    auth_service = _auth_service(request)
    if auth_service.is_device_blacklisted(payload.device_id):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "device_blacklisted",
                "message": "This device is blocked by the administrator",
            },
        )
    try:
        user_id = pairing_service.verify_session_proof(
            device_id=payload.device_id,
            challenge=payload.challenge,
            proof=payload.proof,
        )
    except DevicePairingError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    service = _auth_service(request)
    try:
        result = service.login_by_user_id(user_id=user_id)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    _activity_log(request).log("device_session", user_id=result.user.user_id, user_login=result.user.login, details=f"device={payload.device_id}")
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

    _activity_log(request).log("register", user_id=result.user.user_id, user_login=result.user.login, details=f"phone={payload.phone}")
    # New accounts are members of the common group chats (they can post in
    # "General" right away). Best-effort: the startup sync backfills.
    try:
        ChatService(request.app.state.data_layer.database_path).ensure_common_chat_membership(
            user_id=result.user.user_id
        )
    except Exception:
        pass
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
    try:
        service.get_session(payload.session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
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
