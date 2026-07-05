from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import TelemetrySnapshotData


HookProvider = Callable[[], Any]


class TelemetryHooksRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, HookProvider] = {}

    def register(self, *, key: str, provider: HookProvider) -> None:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("hook key must not be empty")
        self._providers[normalized_key] = provider

    def unregister(self, *, key: str) -> None:
        self._providers.pop(key.strip(), None)

    def collect(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for key, provider in self._providers.items():
            snapshot[key] = provider()
        return snapshot

    def snapshot_data(
        self,
        *,
        watchdog_ok: bool,
        safe_shutdown_ready: bool,
    ) -> TelemetrySnapshotData:
        raw = self.collect()
        return TelemetrySnapshotData(
            vin_mv=_coerce_int(raw.get("power.vin_mv"), default=5000),
            current_ma=_coerce_int(raw.get("power.current_ma"), default=250),
            board_c=_coerce_float(raw.get("temperature.board_c"), default=35.0),
            ambient_c=_coerce_float(raw.get("temperature.ambient_c"), default=28.0),
            watchdog_ok=_coerce_bool(raw.get("service.watchdog_ok"), default=watchdog_ok),
            safe_shutdown_ready=_coerce_bool(
                raw.get("service.safe_shutdown_ready"),
                default=safe_shutdown_ready,
            ),
        )


def _coerce_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _coerce_float(value: Any, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default
