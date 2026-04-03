from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class GatewayError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CommandSender(Protocol):
    def send(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class UrllibCommandSender:
    base_url: str
    timeout_s: float = 5.0

    def send(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._build_url(path=path, query=query)
        body: bytes | None = None
        headers = {"accept": "application/json"}

        if json_payload is not None:
            body = json.dumps(json_payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
            headers["content-type"] = "application/json"

        request = urllib.request.Request(url=url, method=method.upper(), data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = response.read().decode("utf-8")
                return self._decode_json(payload)
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
            raise GatewayError(
                code="http_error",
                message=f"HTTP {exc.code} for {method} {path}: {details}",
                status_code=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise GatewayError(code="network_error", message=f"Network error for {method} {path}: {exc}") from exc

    def _build_url(self, *, path: str, query: Mapping[str, str] | None) -> str:
        base = self.base_url.rstrip("/")
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{base}{normalized_path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        return url

    @staticmethod
    def _decode_json(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GatewayError(code="invalid_json", message=f"Invalid JSON response: {exc}") from exc

        if not isinstance(parsed, dict):
            raise GatewayError(code="invalid_json", message="JSON response must be an object")
        return parsed


class ServerOpsGateway:
    def __init__(self, sender: CommandSender) -> None:
        self._sender = sender

    @property
    def sender(self) -> CommandSender:
        return self._sender

    def health(self) -> dict[str, Any]:
        return self._sender.send(method="GET", path="/health")

    def runtime_state(self, *, session_token: str) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/ops/api/state",
            query={"session_token": session_token},
        )

    def set_degraded_mode(
        self,
        *,
        session_token: str,
        enabled: bool,
        reason: str,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path="/ops/api/degraded-mode",
            json_payload={
                "session_token": session_token,
                "enabled": enabled,
                "reason": reason,
            },
        )

    def shutdown_dry_run(self, *, session_token: str, reason: str) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path="/ops/api/shutdown/dry-run",
            json_payload={
                "session_token": session_token,
                "reason": reason,
            },
        )

    def register_device(
        self,
        *,
        session_token: str,
        device_id: str,
        device_type: str,
        boot_id: str | None,
        transport: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_token": session_token,
            "device_id": device_id,
            "device_type": device_type,
        }
        if boot_id is not None:
            payload["boot_id"] = boot_id
        if transport is not None:
            payload["transport"] = transport
        if metadata:
            payload["metadata"] = dict(metadata)
        return self._sender.send(
            method="POST",
            path="/ops/api/devices/register",
            json_payload=payload,
        )

    def send_heartbeat(
        self,
        *,
        session_token: str,
        device_id: str,
        device_type: str,
        heartbeat_status: str,
        uptime_ms: int,
        queue_depth: int,
        metrics: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_token": session_token,
            "device_id": device_id,
            "device_type": device_type,
            "heartbeat_status": heartbeat_status,
            "uptime_ms": int(uptime_ms),
            "queue_depth": int(queue_depth),
        }
        if metrics:
            payload["metrics"] = dict(metrics)
        return self._sender.send(
            method="POST",
            path="/ops/api/devices/heartbeat",
            json_payload=payload,
        )

    def send_telemetry(
        self,
        *,
        session_token: str,
        device_id: str,
        device_type: str,
        snapshot: Mapping[str, Any],
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_token": session_token,
            "device_id": device_id,
            "device_type": device_type,
            "snapshot": dict(snapshot),
        }
        if source_message_id is not None:
            payload["source_message_id"] = source_message_id
        return self._sender.send(
            method="POST",
            path="/ops/api/devices/telemetry",
            json_payload=payload,
        )

    def device_status(self, *, session_token: str, device_id: str) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path=f"/ops/api/devices/{device_id}/status",
            query={"session_token": session_token},
        )
