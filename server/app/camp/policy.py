"""Camp-specific communication and child-safety policy.

The core chat service is intentionally kept generic.  Camp Edition applies
these rules at the camp API boundary and exposes the decisions to the UI, so
a camp deployment can be reviewed and tested without changing the shared chat
domain model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping

AGE_BANDS = ("under10", "10_13", "14_17", "adult")
CAMP_ROLES = (
    "child",
    "counselor",
    "director",
    "security",
    "medic",
    "parent",
    "it",
    "kitchen",
)
STAFF_ROLES = {"counselor", "director", "security", "medic", "it", "kitchen"}
ADULT_ROLES = STAFF_ROLES | {"parent"}

DEFAULT_QUIET_START_MINUTES = 21 * 60 + 30
DEFAULT_QUIET_END_MINUTES = 7 * 60 + 30


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    message: str
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "allowed": self.allowed,
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def _allow(code: str = "allowed", message: str = "Allowed") -> PolicyDecision:
    return PolicyDecision(True, code, message)


def _deny(code: str, message: str, **details: Any) -> PolicyDecision:
    return PolicyDecision(False, code, message, details or None)


def age_band_for_age(age: int) -> str:
    if age < 0:
        raise ValueError("age must not be negative")
    if age < 10:
        return "under10"
    if age < 14:
        return "10_13"
    if age < 18:
        return "14_17"
    return "adult"


def age_band_from_birth_date(value: str | None, *, at: date | None = None) -> str | None:
    """Return an age band from an ISO date, or None for an empty value."""

    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        born = date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError("birth_date must be YYYY-MM-DD") from exc
    today = at or datetime.now(tz=timezone.utc).date()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if years < 0 or years > 120:
        raise ValueError("birth_date is outside the supported range")
    return age_band_for_age(years)


def _setting(settings: Mapping[str, Any] | Any, key: str, default: Any) -> Any:
    if isinstance(settings, Mapping):
        return settings.get(key, default)
    return getattr(settings, key, default)


def is_quiet_hours(minute_of_day: int, settings: Mapping[str, Any] | Any) -> bool:
    if not 0 <= minute_of_day <= 1439:
        raise ValueError("minute_of_day must be between 0 and 1439")
    start = int(_setting(settings, "quiet_start_minutes", DEFAULT_QUIET_START_MINUTES))
    end = int(_setting(settings, "quiet_end_minutes", DEFAULT_QUIET_END_MINUTES))
    if start == end:
        return False
    if start < end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


def _role(person: Mapping[str, Any] | Any) -> str:
    return str(_setting(person, "role", ""))


def _band(person: Mapping[str, Any] | Any) -> str:
    return str(_setting(person, "age_band", "adult"))


def check_direct_message(
    actor: Mapping[str, Any] | Any,
    target: Mapping[str, Any] | Any,
    settings: Mapping[str, Any] | Any,
) -> PolicyDecision:
    """Camp children never get free-form DMs with adults.

    Child↔child DMs are opt-in per session and only within the same age band.
    """

    actor_role = _role(actor)
    target_role = _role(target)
    actor_band = _band(actor)
    target_band = _band(target)

    if actor_role == "child" and target_role != "child":
        return _deny(
            "child_staff_dm_blocked",
            "Use the counselor request button instead of a private message",
        )
    if target_role == "child" and actor_role != "child":
        return _deny(
            "adult_child_dm_blocked",
            "Adults cannot start private chats with children",
        )
    if actor_role == "child" and target_role == "child":
        if not bool(_setting(settings, "allow_child_dm", False)):
            return _deny(
                "child_dm_disabled",
                "Private chats between children are disabled in this camp",
            )
        if actor_band != target_band:
            return _deny(
                "mixed_age_dm_blocked",
                "Private chats are only allowed within the same age band",
            )
        if bool(_setting(settings, "require_two_adults_for_dm", True)):
            return _deny(
                "adult_oversight_required",
                "A child private chat requires a counselor-created supervised room",
            )
        return _allow()
    if actor_role == "parent" or target_role == "parent":
        return _deny(
            "parent_dm_blocked",
            "Parents use the digest and the counselor request queue",
        )
    return _allow()


def check_media(
    actor: Mapping[str, Any] | Any,
    settings: Mapping[str, Any] | Any,
    *,
    has_consent: bool = False,
) -> PolicyDecision:
    role = _role(actor)
    band = _band(actor)
    if role != "child":
        if role in STAFF_ROLES:
            return _allow()
        return _deny("media_staff_only", "Only camp staff can publish camp media")

    if band in {"under10", "10_13"}:
        return _deny(
            "child_media_age_blocked",
            "Photos and videos are disabled for children under 14",
        )
    if not bool(_setting(settings, "allow_child_media", False)):
        return _deny("child_media_disabled", "Child media uploads are disabled")
    if not has_consent:
        return _deny("media_consent_required", "A photo consent is required")
    return _allow()


def check_forward(actor: Mapping[str, Any] | Any) -> PolicyDecision:
    role = _role(actor)
    if role in STAFF_ROLES:
        return _allow()
    return _deny(
        "forward_blocked",
        "Children and parents cannot forward camp messages or media",
    )


def check_post(
    actor: Mapping[str, Any] | Any,
    settings: Mapping[str, Any] | Any,
    *,
    minute_of_day: int,
) -> PolicyDecision:
    role = _role(actor)
    if role in ADULT_ROLES:
        return _allow()
    if is_quiet_hours(minute_of_day, settings):
        return _deny(
            "quiet_hours",
            "Children's chat is read-only during quiet hours",
            quiet_start_minutes=int(
                _setting(settings, "quiet_start_minutes", DEFAULT_QUIET_START_MINUTES)
            ),
            quiet_end_minutes=int(
                _setting(settings, "quiet_end_minutes", DEFAULT_QUIET_END_MINUTES)
            ),
        )
    return _allow()


def check_group_membership(
    actor: Mapping[str, Any] | Any,
    target: Mapping[str, Any] | Any,
) -> PolicyDecision:
    actor_role = _role(actor)
    target_role = _role(target)
    if actor_role in STAFF_ROLES:
        return _allow()
    if actor_role == "child":
        actor_unit = _setting(actor, "unit_id", None)
        target_unit = _setting(target, "unit_id", None)
        if actor_unit is None or actor_unit != target_unit or target_role != "child":
            return _deny(
                "group_scope",
                "Children only see their own squad room",
            )
        return _allow()
    return _deny("group_scope", "This role has no camp group access")


def check_request(actor: Mapping[str, Any] | Any) -> PolicyDecision:
    if _role(actor) == "child":
        return _allow()
    return _deny(
        "request_child_only",
        "A counselor request can only be created by a child",
    )
