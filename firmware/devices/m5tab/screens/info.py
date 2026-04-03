from __future__ import annotations

from typing import Any, Mapping

from ..models import InfoScreenData


def build_info_screen(*, telemetry_bundle: Mapping[str, Any], generated_at_ms: int) -> InfoScreenData:
    health = _mapping(telemetry_bundle.get("health"))
    readiness = _mapping(telemetry_bundle.get("readiness"))
    mode = _mapping(telemetry_bundle.get("mode"))
    runtime = _mapping(telemetry_bundle.get("runtime"))
    incidents = _mapping(telemetry_bundle.get("incidents"))

    health_runtime = _mapping(health.get("runtime"))
    runtime_payload = _mapping(runtime.get("runtime"))
    readiness_checks = _mapping(readiness.get("checks"))
    data_layer = _mapping(readiness.get("data_layer"))

    runtime_degraded_mode = _bool(
        runtime_payload.get("degraded_mode"),
        default=_bool(health_runtime.get("degraded_mode"), default=False),
    )
    active_incidents_count = _int_or_none(incidents.get("count"))

    return InfoScreenData(
        health_status=_string(health.get("status"), default="unknown"),
        readiness_status=_string(readiness.get("status"), default="unknown"),
        profile=_string(health.get("profile"), default="unknown"),
        uptime_ms=_int(health.get("uptime_ms"), default=0),
        access_mode=_string(mode.get("access_mode"), default="unknown"),
        runtime_degraded_mode=runtime_degraded_mode,
        data_layer_initialized=_bool(
            readiness_checks.get("data_layer_initialized"),
            default=False,
        ),
        applied_migrations=_int(data_layer.get("applied_migrations"), default=0),
        active_incidents_count=active_incidents_count,
        generated_at_ms=generated_at_ms,
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string(value: Any, *, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default


def _int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
