from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.models import ClientKind, UserRole
from app.models.internet_access import WiFiInterfaceRole
from app.services.auth import AuthError, AuthService
from app.services.network_service import NetworkService


router = APIRouter(prefix="/admin/network", tags=["admin-network"])


@router.get("/panel", include_in_schema=False)
async def admin_network_panel() -> RedirectResponse:
    # Старая token-панель заменена единой админкой /admin.
    return RedirectResponse("/admin", status_code=302)


class WiFiConnectRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    ssid: str = Field(min_length=1, max_length=64)
    password: str = Field(max_length=128)
    interface: str | None = Field(default=None, max_length=16)


class WiFiDisconnectRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


class InternetAccessRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    user_id: int
    enabled: bool = True


class InterfaceRoleRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    ifname: str = Field(min_length=3, max_length=16)
    role: WiFiInterfaceRole


def _template_path() -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "admin" / "network" / "index.html"


def _auth_service(request: Request) -> AuthService:
    return AuthService(db_path=request.app.state.data_layer.database_path)


def _network_service(request: Request) -> NetworkService:
    return NetworkService(db_path=request.app.state.data_layer.database_path)


def _resolve_admin(request: Request, session_token: str) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail={"code": "admin_only", "message": "Admin role is required"})
    if session.user.user_id is None:
        raise HTTPException(status_code=500, detail={"code": "invalid_user", "message": "Missing user id"})
    return session.user.user_id


@router.get("", response_class=HTMLResponse)
async def network_admin_page() -> HTMLResponse:
    return HTMLResponse(content=_template_path().read_text(encoding="utf-8"))


# --- Interface management ---

@router.get("/interfaces")
async def list_interfaces(request: Request, session_token: str = Query(..., min_length=8, max_length=512)) -> dict[str, object]:
    _resolve_admin(request, session_token)
    svc = _network_service(request)
    interfaces = svc.detect_interfaces()
    return {
        "status": "ok",
        "count": len(interfaces),
        "items": [
            {"ifname": i.ifname, "role": i.role.value, "priority": i.priority,
             "chipset": i.chipset, "tx_power_dbm": i.tx_power_dbm, "mac": i.mac_address}
            for i in interfaces
        ],
    }


@router.post("/interfaces/assign")
async def assign_interface_role(request: Request, payload: InterfaceRoleRequest) -> dict[str, object]:
    _resolve_admin(request, payload.session_token)
    svc = _network_service(request)
    svc.set_interface_role(payload.ifname, payload.role)
    interfaces = svc.detect_interfaces()
    return {
        "status": "ok",
        "items": [
            {"ifname": i.ifname, "role": i.role.value}
            for i in interfaces
        ],
    }


class TxPowerRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    ifname: str
    power_dbm: int = Field(ge=1, le=33)


@router.post("/interfaces/txpower")
async def set_tx_power(request: Request, payload: TxPowerRequest) -> dict[str, object]:
    _resolve_admin(request, payload.session_token)
    svc = _network_service(request)
    ok = svc.set_tx_power(payload.ifname, payload.power_dbm)
    return {"status": "ok" if ok else "error"}


@router.post("/services/restart")
async def restart_services(request: Request, session_token: str = Query(..., min_length=8, max_length=512)) -> dict[str, object]:
    _resolve_admin(request, session_token)
    svc = _network_service(request)
    result = svc.restart_services()
    return result


class NetworkConfigSaveRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    config: dict[str, str] = Field(default_factory=dict)


_ROLE_ALIASES: dict[str, WiFiInterfaceRole] = {
    "ap": WiFiInterfaceRole.AP,
    "client": WiFiInterfaceRole.UPLINK,
    "uplink": WiFiInterfaceRole.UPLINK,
    "off": WiFiInterfaceRole.UNASSIGNED,
    "unassigned": WiFiInterfaceRole.UNASSIGNED,
}


@router.post("/config/save")
async def save_network_config(request: Request, payload: NetworkConfigSaveRequest) -> dict[str, object]:
    """Apply AP/Client/Off role changes for one or more interfaces (used by the admin UI)."""
    _resolve_admin(request, payload.session_token)
    if not payload.config:
        raise HTTPException(status_code=422, detail={"code": "empty_config", "message": "config must not be empty"})
    roles: dict[str, WiFiInterfaceRole] = {}
    for ifname, raw_role in payload.config.items():
        role = _ROLE_ALIASES.get(str(raw_role).strip().lower())
        if role is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_role", "message": f"Invalid role '{raw_role}' for interface {ifname}"},
            )
        roles[str(ifname)] = role
    svc = _network_service(request)
    svc.set_interface_roles(roles)
    return {
        "status": "ok",
        "changed": [{"ifname": name, "role": role.value} for name, role in roles.items()],
    }


# --- WiFi management ---

@router.get("/wifi/scan")
async def scan_wifi(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    interface: str | None = Query(default=None, max_length=16),
) -> dict[str, object]:
    _resolve_admin(request, session_token)
    svc = _network_service(request)
    networks = svc.scan_wifi(interface=interface)
    return {"status": "ok", "count": len(networks), "interface": svc.get_uplink_iface(),
            "networks": [{"ssid": n.ssid, "signal": n.signal_strength, "security": n.security} for n in networks]}


@router.post("/wifi/connect")
async def connect_wifi(request: Request, payload: WiFiConnectRequest) -> dict[str, object]:
    _resolve_admin(request, payload.session_token)
    svc = _network_service(request)
    ok = svc.connect_wifi(payload.ssid, payload.password, interface=payload.interface)
    status = svc.get_uplink_status()
    return {"status": "ok" if ok else "error", "connected": status.connected,
            "ssid": status.ssid, "ip_address": status.ip_address}


@router.post("/wifi/disconnect")
async def disconnect_wifi(request: Request, payload: WiFiDisconnectRequest) -> dict[str, object]:
    _resolve_admin(request, payload.session_token)
    svc = _network_service(request)
    svc.disconnect_wifi()
    return {"status": "ok", "connected": False}


@router.get("/wifi/status")
async def wifi_status(request: Request, session_token: str = Query(..., min_length=8, max_length=512)) -> dict[str, object]:
    _resolve_admin(request, session_token)
    svc = _network_service(request)
    status = svc.get_uplink_status()
    return {"status": "ok", "connected": status.connected, "ssid": status.ssid,
            "interface": status.interface_name, "ip_address": status.ip_address}


# --- Per-user internet access ---

@router.get("/users")
async def list_users_internet(request: Request, session_token: str = Query(..., min_length=8, max_length=512)) -> dict[str, object]:
    _resolve_admin(request, session_token)
    svc = _network_service(request)
    records = svc.get_all_internet_access()
    import sqlite3
    conn = sqlite3.connect(request.app.state.data_layer.database_path)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id, login, role, status FROM users ORDER BY id").fetchall()
    conn.close()
    access_map = {r.user_id: r for r in records}
    items = [{"user_id": u["id"], "login": u["login"], "role": u["role"],
              "internet_enabled": access_map[u["id"]].enabled if u["id"] in access_map else False,
              "granted_at_ms": access_map[u["id"]].granted_at_ms if u["id"] in access_map else 0}
             for u in users]
    return {"status": "ok", "count": len(items), "items": items}


@router.post("/users/internet")
async def toggle_user_internet(request: Request, payload: InternetAccessRequest) -> dict[str, object]:
    admin_id = _resolve_admin(request, payload.session_token)
    svc = _network_service(request)
    svc.set_user_internet(payload.user_id, payload.enabled, admin_id)
    rec = svc.get_user_internet(payload.user_id)
    return {"status": "ok", "user_id": rec.user_id, "internet_enabled": rec.enabled}
