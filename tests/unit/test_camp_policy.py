from __future__ import annotations

from app.camp.policy import (
    age_band_for_age,
    age_band_from_birth_date,
    check_direct_message,
    check_forward,
    check_media,
    check_post,
    is_quiet_hours,
)


SETTINGS = {
    "quiet_start_minutes": 1290,
    "quiet_end_minutes": 450,
    "allow_child_dm": False,
    "allow_child_media": False,
    "require_two_adults_for_dm": True,
}


def test_age_bands() -> None:
    assert age_band_for_age(9) == "under10"
    assert age_band_for_age(10) == "10_13"
    assert age_band_for_age(13) == "10_13"
    assert age_band_for_age(14) == "14_17"
    assert age_band_for_age(17) == "14_17"
    assert age_band_for_age(18) == "adult"
    assert age_band_from_birth_date("2012-05-01", at=__import__("datetime").date(2026, 11, 13)) == "14_17"


def test_quiet_hours_wrap_midnight() -> None:
    assert is_quiet_hours(1290, SETTINGS) is True
    assert is_quiet_hours(23 * 60, SETTINGS) is True
    assert is_quiet_hours(7 * 60 + 29, SETTINGS) is True
    assert is_quiet_hours(7 * 60 + 30, SETTINGS) is False
    assert is_quiet_hours(12 * 60, SETTINGS) is False


def test_child_cannot_dm_staff_and_child_dm_is_opt_in() -> None:
    child = {"role": "child", "age_band": "10_13", "unit_id": 1}
    counselor = {"role": "counselor", "age_band": "adult", "unit_id": 1}
    other_child = {"role": "child", "age_band": "10_13", "unit_id": 1}
    assert check_direct_message(child, counselor, SETTINGS).code == "child_staff_dm_blocked"
    assert check_direct_message(child, other_child, SETTINGS).code == "child_dm_disabled"

    relaxed = {**SETTINGS, "allow_child_dm": True, "require_two_adults_for_dm": False}
    assert check_direct_message(child, other_child, relaxed).allowed is True
    mixed = {"role": "child", "age_band": "14_17", "unit_id": 1}
    assert check_direct_message(child, mixed, relaxed).code == "mixed_age_dm_blocked"


def test_media_policy_requires_age_and_consent() -> None:
    young = {"role": "child", "age_band": "10_13", "unit_id": 1}
    teen = {"role": "child", "age_band": "14_17", "unit_id": 1}
    assert check_media(young, SETTINGS, has_consent=True).code == "child_media_age_blocked"
    assert check_media(teen, SETTINGS, has_consent=True).code == "child_media_disabled"
    allowed_settings = {**SETTINGS, "allow_child_media": True}
    assert check_media(teen, allowed_settings, has_consent=False).code == "media_consent_required"
    assert check_media(teen, allowed_settings, has_consent=True).allowed is True


def test_forward_and_quiet_post_rules() -> None:
    child = {"role": "child", "age_band": "10_13", "unit_id": 1}
    counselor = {"role": "counselor", "age_band": "adult", "unit_id": 1}
    assert check_forward(child).allowed is False
    assert check_forward(counselor).allowed is True
    assert check_post(child, SETTINGS, minute_of_day=22 * 60).code == "quiet_hours"
    assert check_post(child, SETTINGS, minute_of_day=12 * 60).allowed is True
    assert check_post(counselor, SETTINGS, minute_of_day=22 * 60).allowed is True
