from __future__ import annotations

from dataclasses import dataclass

from .models import DiagnosticsReport


@dataclass(frozen=True)
class RecordedError:
    code: str
    message: str
    occurred_at_ms: int


class DiagnosticsCollector:
    def __init__(self) -> None:
        self._last_error: RecordedError | None = None

    def record_error(self, *, code: str, message: str, occurred_at_ms: int) -> None:
        normalized_code = code.strip()
        normalized_message = message.strip()
        if not normalized_code:
            normalized_code = "unknown_error"
        if not normalized_message:
            normalized_message = "unknown error"
        self._last_error = RecordedError(
            code=normalized_code,
            message=normalized_message,
            occurred_at_ms=occurred_at_ms,
        )

    def clear_error(self) -> None:
        self._last_error = None

    def build_report(
        self,
        *,
        watchdog_ok: bool,
        watchdog_missed_count: int,
        queue_depth: int,
        network_ok: bool,
        generated_at_ms: int,
    ) -> DiagnosticsReport:
        return DiagnosticsReport(
            watchdog_ok=watchdog_ok,
            watchdog_missed_count=watchdog_missed_count,
            queue_depth=queue_depth,
            last_error_code=self._last_error.code if self._last_error is not None else None,
            last_error_message=self._last_error.message if self._last_error is not None else None,
            network_ok=network_ok,
            generated_at_ms=generated_at_ms,
        )
