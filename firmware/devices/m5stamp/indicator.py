from __future__ import annotations

from .models import HeartbeatStatus, IndicatorPattern, IndicatorState


class IndicatorController:
    def __init__(self) -> None:
        self._state = IndicatorState(
            pattern=IndicatorPattern.STEADY_GREEN,
            brightness_pct=40,
            blink_interval_ms=None,
        )

    @property
    def state(self) -> IndicatorState:
        return self._state

    def apply_status(self, *, status: HeartbeatStatus, network_ok: bool) -> IndicatorState:
        if not network_ok and status == HeartbeatStatus.OK:
            self._state = IndicatorState(
                pattern=IndicatorPattern.BLINK_BLUE_SLOW,
                brightness_pct=45,
                blink_interval_ms=1200,
            )
            return self._state

        if status == HeartbeatStatus.HOLD_STATE:
            self._state = IndicatorState(
                pattern=IndicatorPattern.BLINK_RED_FAST,
                brightness_pct=95,
                blink_interval_ms=200,
            )
            return self._state

        if status == HeartbeatStatus.DEGRADED:
            self._state = IndicatorState(
                pattern=IndicatorPattern.BLINK_YELLOW,
                brightness_pct=70,
                blink_interval_ms=700,
            )
            return self._state

        self._state = IndicatorState(
            pattern=IndicatorPattern.STEADY_GREEN,
            brightness_pct=40,
            blink_interval_ms=None,
        )
        return self._state
