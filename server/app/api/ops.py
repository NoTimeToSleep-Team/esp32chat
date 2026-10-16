from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import (
    BackupRecord,
    BackupRestorePlan,
    ClientKind,
    IncidentLevel,
    IncidentRecord,
    IncidentStatus,
    RuntimeState,
    ShutdownRunRecord,
    UserRole,
)
from app.services.auth import AuthError, AuthService
from app.services.backup import BackupError, BackupService
from app.services.incidents import IncidentError, IncidentService
from app.services.shutdown import ShutdownError, ShutdownService




class RestartServiceRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    service: str = Field(min_length=1, max_length=64)


router = APIRouter(tags=["ops"])


class BackupRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    reason: str | None = Field(default=None, max_length=2048)


class RestoreDryRunRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    backup_name: str = Field(min_length=1, max_length=256)


class SetDegradedModeRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    enabled: bool
    reason: str | None = Field(default=None, max_length=2048)


class ShutdownDryRunRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    reason: str | None = Field(default=None, max_length=2048)


class CreateIncidentRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    level: IncidentLevel = IncidentLevel.WARNING
    title: str = Field(min_length=1, max_length=256)
    source: str | None = Field(default=None, max_length=128)
    details: dict[str, object] | None = None


class ResolveIncidentRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    resolution_note: str | None = Field(default=None, max_length=2048)


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _backup_service(request: Request) -> BackupService:
    data_layer = request.app.state.data_layer
    return BackupService(
        db_path=data_layer.database_path,
        storage_root=data_layer.storage_root,
    )


def _incident_service(request: Request) -> IncidentService:
    data_layer = request.app.state.data_layer
    return IncidentService(db_path=data_layer.database_path)


def _shutdown_service(request: Request) -> ShutdownService:
    data_layer = request.app.state.data_layer
    return ShutdownService(db_path=data_layer.database_path)


def _resolve_admin_user_id(request: Request, session_token: str) -> int:
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

    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Admin user id is missing"},
        )

    return session.user.user_id


def _raise_backup_error(exc: BackupError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _raise_incident_error(exc: IncidentError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _raise_shutdown_error(exc: ShutdownError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _backup_payload(record: BackupRecord) -> dict[str, object]:
    return {
        "backup_id": record.backup_id,
        "backup_name": record.backup_name,
        "backup_path": record.backup_path,
        "status": record.status.value,
        "reason": record.reason,
        "trigger_kind": record.trigger_kind,
        "actor_user_id": record.actor_user_id,
        "created_at_ms": record.created_at_ms,
        "completed_at_ms": record.completed_at_ms,
        "size_bytes": record.size_bytes,
        "checksum_sha256": record.checksum_sha256,
        "error_message": record.error_message,
    }


def _restore_plan_payload(plan: BackupRestorePlan) -> dict[str, object]:
    return {
        "backup_name": plan.backup_name,
        "backup_path": plan.backup_path,
        "database_path": plan.database_path,
        "backup_size_bytes": plan.backup_size_bytes,
        "dry_run": plan.dry_run,
    }


def _runtime_state_payload(state: RuntimeState) -> dict[str, object]:
    return {
        "degraded_mode": state.degraded_mode,
        "reason": state.reason,
        "updated_by_user_id": state.updated_by_user_id,
        "updated_at_ms": state.updated_at_ms,
    }


def _incident_payload(record: IncidentRecord) -> dict[str, object]:
    return {
        "incident_id": record.incident_id,
        "incident_key": record.incident_key,
        "level": record.level.value,
        "title": record.title,
        "details_json": record.details_json,
        "source": record.source,
        "status": record.status.value,
        "created_at_ms": record.created_at_ms,
        "updated_at_ms": record.updated_at_ms,
        "resolved_at_ms": record.resolved_at_ms,
        "created_by_user_id": record.created_by_user_id,
        "resolved_by_user_id": record.resolved_by_user_id,
        "resolution_note": record.resolution_note,
    }


def _shutdown_run_payload(record: ShutdownRunRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "run_kind": record.run_kind.value,
        "requested_by_user_id": record.requested_by_user_id,
        "reason": record.reason,
        "status": record.status.value,
        "started_at_ms": record.started_at_ms,
        "finished_at_ms": record.finished_at_ms,
        "steps_json": record.steps_json,
    }


@router.get("/ops/api/state")
async def get_ops_state(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    service = _shutdown_service(request)

    try:
        state = service.get_runtime_state()
    except ShutdownError as exc:
        _raise_shutdown_error(exc)

    return {"status": "ok", "runtime": _runtime_state_payload(state)}


@router.post("/ops/api/degraded-mode")
async def set_degraded_mode(request: Request, payload: SetDegradedModeRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _shutdown_service(request)

    try:
        state = service.set_degraded_mode(
            actor_user_id=admin_user_id,
            enabled=payload.enabled,
            reason=payload.reason,
        )
    except ShutdownError as exc:
        _raise_shutdown_error(exc)

    return {"status": "ok", "runtime": _runtime_state_payload(state)}


@router.get("/ops/api/backups")
async def list_backups(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _backup_service(request)

    try:
        backups = service.list_backups(actor_user_id=admin_user_id, limit=limit, offset=offset)
    except BackupError as exc:
        _raise_backup_error(exc)

    return {
        "status": "ok",
        "count": len(backups),
        "items": [_backup_payload(item) for item in backups],
    }


@router.post("/ops/api/backups")
async def create_backup(request: Request, payload: BackupRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _backup_service(request)

    try:
        backup = service.create_backup(actor_user_id=admin_user_id, reason=payload.reason, dry_run=False)
    except BackupError as exc:
        _raise_backup_error(exc)

    return {"status": "ok", "backup": _backup_payload(backup)}


@router.post("/ops/api/backups/dry-run")
async def backup_dry_run(request: Request, payload: BackupRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _backup_service(request)

    try:
        backup = service.create_backup(actor_user_id=admin_user_id, reason=payload.reason, dry_run=True)
    except BackupError as exc:
        _raise_backup_error(exc)

    return {"status": "ok", "backup": _backup_payload(backup)}


@router.post("/ops/api/backups/restore/dry-run")
async def restore_dry_run(request: Request, payload: RestoreDryRunRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _backup_service(request)

    try:
        plan = service.restore_dry_run(actor_user_id=admin_user_id, backup_name=payload.backup_name)
    except BackupError as exc:
        _raise_backup_error(exc)

    return {"status": "ok", "plan": _restore_plan_payload(plan)}


@router.get("/ops/api/incidents")
async def list_incidents(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: IncidentStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _incident_service(request)

    try:
        incidents = service.list_incidents(
            actor_user_id=admin_user_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except IncidentError as exc:
        _raise_incident_error(exc)

    return {
        "status": "ok",
        "count": len(incidents),
        "items": [_incident_payload(item) for item in incidents],
    }


@router.post("/ops/api/incidents")
async def create_incident(request: Request, payload: CreateIncidentRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _incident_service(request)

    try:
        incident = service.create_incident(
            actor_user_id=admin_user_id,
            level=payload.level,
            title=payload.title,
            details=payload.details,
            source=payload.source,
        )
    except IncidentError as exc:
        _raise_incident_error(exc)

    return {"status": "ok", "incident": _incident_payload(incident)}


@router.post("/ops/api/incidents/{incident_id}/resolve")
async def resolve_incident(
    request: Request,
    incident_id: int,
    payload: ResolveIncidentRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _incident_service(request)

    try:
        incident = service.resolve_incident(
            actor_user_id=admin_user_id,
            incident_id=incident_id,
            resolution_note=payload.resolution_note,
        )
    except IncidentError as exc:
        _raise_incident_error(exc)

    return {"status": "ok", "incident": _incident_payload(incident)}


@router.get("/ops/api/shutdown/runs")
async def list_shutdown_runs(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _shutdown_service(request)

    try:
        runs = service.list_shutdown_runs(actor_user_id=admin_user_id, limit=limit, offset=offset)
    except ShutdownError as exc:
        _raise_shutdown_error(exc)

    return {
        "status": "ok",
        "count": len(runs),
        "items": [_shutdown_run_payload(item) for item in runs],
    }


@router.post("/ops/api/shutdown/dry-run")
async def shutdown_dry_run(request: Request, payload: ShutdownDryRunRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _shutdown_service(request)

    try:
        run = service.run_shutdown_dry(actor_user_id=admin_user_id, reason=payload.reason)
    except ShutdownError as exc:
        _raise_shutdown_error(exc)

    return {"status": "ok", "run": _shutdown_run_payload(run)}


# === System health & restart ===

@router.get("/ops/api/system-health")
async def get_system_health(request: Request, session_token: str = Query(..., min_length=8, max_length=512)):
    _resolve_admin_user_id(request, session_token)
    info = {}
    # CPU temperature: prefer the kernel thermal zone (readable without extra
    # permissions), fall back to vcgencmd when available.
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as fh:
            milli = int(fh.read().strip())
        info["cpu_temp"] = "%.1f C" % (milli / 1000.0)
    except Exception:
        try:
            import subprocess
            r = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=5)
            temp = r.stdout.strip().replace("temp=", "").replace("'C", " C")
            info["cpu_temp"] = temp if (r.returncode == 0 and temp) else "?"
        except Exception:
            info["cpu_temp"] = "?"
    try:
        import subprocess
        r = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().split("\n")[1].split()
        info["ram_total"] = parts[1] + " MB"
        info["ram_used"] = parts[2] + " MB"
    except:
        info["ram_total"] = "?"
        info["ram_used"] = "?"
    try:
        import subprocess
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().split("\n")[1].split()
        info["disk_total"] = parts[1]
        info["disk_used"] = parts[2]
        info["disk_pct"] = parts[4]
    except:
        info["disk_total"] = "?"
        info["disk_used"] = "?"
        info["disk_pct"] = "?"
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as fh:
            up_s = int(float(fh.read().split()[0]))
        days, rem = divmod(up_s, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        info["uptime"] = ("%dд " % days if days else "") + "%dч %dм" % (hours, mins)
    except Exception:
        info["uptime"] = "?"
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as fh:
            info["load1"] = fh.read().split()[0]
    except Exception:
        info["load1"] = "?"
    return {"status": "ok", "health": info}


class SyncTimeRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    client_time_ms: int = Field(ge=0)


@router.post("/ops/api/sync-time")
async def sync_time(request: Request, payload: SyncTimeRequest):
    """Align the board clock with the client's clock (staff only).

    The Pi has no RTC battery and there is no internet for NTP on this
    network, so an admin device with an accurate clock is the best source.
    Only adjusts when the difference is meaningful (> 2s).
    """
    _resolve_admin_user_id(request, payload.session_token)
    import time

    before_ms = int(time.time() * 1000)
    offset_ms = int(payload.client_time_ms) - before_ms
    adjusted = False
    message = "Время точное"
    if abs(offset_ms) > 2000:
        target_epoch = payload.client_time_ms / 1000.0
        result = _sudo_run(["date", "-s", "@%.3f" % target_epoch])
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", "replace").strip()
            raise HTTPException(status_code=500, detail={"code": "clock_set_failed", "message": err[:300] or "sudo failed"})
        adjusted = True
        message = "Время синхронизировано"
    after_ms = int(time.time() * 1000)
    return {
        "status": "ok",
        "offset_ms": offset_ms,
        "adjusted": adjusted,
        "server_time_ms": after_ms,
        "message": message,
    }


class RestartServiceRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    service: str = Field(min_length=1, max_length=64)


def _sudo_run(cmd: list) -> "subprocess.CompletedProcess":
    """Run a command via sudo: passwordless first, LC_SUDO_PASSWORD as fallback."""
    import os
    import subprocess

    result = subprocess.run(["sudo", "-n"] + cmd, capture_output=True, timeout=30)
    if result.returncode == 0:
        return result
    sudo_pass = os.environ.get("LC_SUDO_PASSWORD", "")
    if sudo_pass:
        result = subprocess.run(
            ["sudo", "-S"] + cmd,
            input=(sudo_pass + "\n").encode(),
            capture_output=True,
            timeout=30,
        )
    return result


@router.post("/ops/api/restart-service")
async def restart_service(request: Request, payload: RestartServiceRequest):
    _resolve_admin_user_id(request, payload.session_token)
    allowed = ["local-chat-server", "local-chat-proxy", "hostapd", "dnsmasq", "ssh", "wpa_supplicant", "bluetooth", "cron", "NetworkManager", "lc-iptables-restore", "lc-network-boot", "systemd-timesyncd"]
    if payload.service not in allowed:
        raise HTTPException(status_code=400, detail={"code": "bad_service", "message": "Allowed: " + ", ".join(allowed)})

    try:
        result = _sudo_run(["systemctl", "restart", payload.service])
        if result.returncode != 0:
            message = (result.stderr or b"").decode("utf-8", "replace").strip() or "sudo failed"
            raise HTTPException(status_code=500, detail={"code": "restart_failed", "message": message[:300]})
        return {"status": "ok", "service": payload.service}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "restart_failed", "message": str(e)})


# === System management ===

@router.get("/ops/api/services")
async def list_services(request: Request, session_token: str = Query(..., min_length=8, max_length=512)):
    _resolve_admin_user_id(request, session_token)
    import subprocess
    svcs = []
    names = ["local-chat-server", "local-chat-proxy", "hostapd", "dnsmasq", 
             "ssh", "wpa_supplicant", "bluetooth", "cron", "NetworkManager",
             "lc-iptables-restore", "lc-network-boot", "systemd-timesyncd"]
    for name in names:
        try:
            r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
            status = r.stdout.strip()
            r2 = subprocess.run(["systemctl", "show", name, "-p", "SubState"], capture_output=True, text=True, timeout=5)
            substate = r2.stdout.strip().replace("SubState=", "")
            svcs.append({"name": name, "active": status, "substate": substate})
        except:
            svcs.append({"name": name, "active": "unknown", "substate": ""})
    return {"status": "ok", "services": svcs}


class RebootRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    confirm: bool = False


@router.post("/ops/api/reboot")
async def reboot_rpi(request: Request, payload: RebootRequest):
    _resolve_admin_user_id(request, payload.session_token)
    if not payload.confirm:
        raise HTTPException(status_code=400, detail={"code": "confirm_required", "message": "Set confirm=true to reboot"})
    import os
    import subprocess
    result = subprocess.run(["sudo", "-n", "reboot"], capture_output=True, timeout=10)
    if result.returncode != 0 and os.environ.get("LC_SUDO_PASSWORD"):
        proc = subprocess.Popen(["sudo", "-S", "reboot"], stdin=subprocess.PIPE)
        proc.communicate((os.environ["LC_SUDO_PASSWORD"] + "\n").encode(), timeout=10)
    return {"status": "ok", "message": "Rebooting..."}
