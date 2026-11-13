from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.camp.service import CampError, CampService
from app.db.migrate import apply_sql_migrations


ADMIN = {
    "user_id": 1,
    "camp_person_id": None,
    "role": "director",
    "session_id": None,
    "unit_id": None,
    "display_name": "Director",
    "age_band": "adult",
}


@pytest.fixture()
def service(tmp_path: Path) -> CampService:
    db_path = tmp_path / "camp_ops.sqlite3"
    apply_sql_migrations(f"sqlite:///{db_path.as_posix()}")
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
            VALUES (?, ?, ?, 'active', 1, 1)
            """,
            [
                ("director", "x", "admin"),
                ("child", "x", "user"),
                ("counselor", "x", "user"),
                ("parent", "x", "user"),
                ("child2", "x", "user"),
            ],
        )
    return CampService(db_path)


def _session(service: CampService):
    session = service.create_session(ADMIN, name="Ops camp", status="active")
    unit = service.create_unit(ADMIN, session_id=session["id"], name="Squad A")
    return session, unit


def _child(service: CampService, session_id: int, unit_id: int, name: str, user_id: int | None = None):
    return service.create_person(
        ADMIN,
        session_id=session_id,
        unit_id=unit_id,
        user_id=user_id,
        role="child",
        age_band="10_13",
        display_name=name,
    )


def _staff(
    service: CampService,
    session_id: int,
    unit_id: int,
    name: str,
    user_id: int,
    role: str = "counselor",
):
    return service.create_person(
        ADMIN,
        session_id=session_id,
        unit_id=unit_id,
        user_id=user_id,
        role=role,
        display_name=name,
    )


def test_attendance_all_present_guard_and_overdue(service: CampService) -> None:
    session, unit = _session(service)
    anya = _child(service, session["id"], unit["id"], "Аня")
    borya = _child(service, session["id"], unit["id"], "Боря")
    event = service.create_attendance_event(ADMIN, unit_id=unit["id"])
    assert event["summary"]["total"] == 2
    assert event["summary"]["unmarked"] == 2

    with pytest.raises(CampError) as exc:
        service.close_attendance(ADMIN, event_id=event["id"])
    assert exc.value.code == "attendance_incomplete"

    after_one = service.mark_attendance(
        ADMIN, event_id=event["id"], person_id=anya["id"], status="present"
    )
    assert after_one["summary"]["present"] == 1
    after_all = service.mark_all_present(ADMIN, event_id=event["id"])
    assert after_all["summary"]["present"] == 2
    assert after_all["summary"]["unmarked"] == 0

    closed = service.close_attendance(ADMIN, event_id=event["id"])
    assert closed["status"] == "closed"
    assert closed["summary"]["total"] == 2

    overdue = service.create_attendance_event(ADMIN, unit_id=unit["id"])
    with sqlite3.connect(service._db_path) as connection:
        connection.execute(
            "UPDATE camp_attendance_events SET deadline_at_ms = 1 WHERE id = ?",
            (overdue["id"],),
        )
    items = service.attendance_overdue(ADMIN)
    assert [item["id"] for item in items] == [overdue["id"]]


def test_alert_playbooks_ack_and_after_action(service: CampService) -> None:
    session, _ = _session(service)
    playbooks = service.list_alert_playbooks(ADMIN)
    assert {item["kind"] for item in playbooks} == {
        "missing_child",
        "evacuation",
        "medical",
        "intruder",
        "lockdown",
    }

    alert = service.start_alert(ADMIN, kind="missing_child", note="Not at roll call")
    assert alert["status"] == "open"
    assert len(alert["steps"]) == 5
    assert alert["ack_count"] == 0

    with pytest.raises(CampError) as exc:
        service.start_alert(ADMIN, kind="missing_child")
    assert exc.value.code == "alert_already_open"

    acked = service.acknowledge_alert(ADMIN, alert_id=alert["id"], step_index=0)
    assert acked["status"] == "acknowledged"
    assert acked["ack_count"] == 1

    closed = service.close_alert(
        ADMIN,
        alert_id=alert["id"],
        after_action="Checked the lake; child was in the art room.",
    )
    assert closed["status"] == "closed"
    assert "art room" in closed["after_action"]

    drill = service.start_alert(ADMIN, kind="evacuation", drill=True)
    assert drill["drill"] == 1
    assert service.start_alert(ADMIN, kind="evacuation", drill=True)["drill"] == 1


def test_zones_scans_last_seen_and_counter(service: CampService) -> None:
    session, unit = _session(service)
    child = _child(service, session["id"], unit["id"], "Аня")
    zone = service.create_zone(ADMIN, name="Main gate", kind="gate")
    first = service.scan_person(ADMIN, zone_id=zone["id"], badge_code=child["badge_code"])
    assert first["person"]["id"] == child["id"]
    service.scan_person(ADMIN, zone_id=zone["id"], person_id=child["id"])

    last = service.last_seen(ADMIN, person_id=child["id"])
    assert last["last_seen"]["zone_name"] == "Main gate"
    monitor = service.zone_monitor(ADMIN)
    row = next(item for item in monitor if item["id"] == zone["id"])
    assert row["scan_count"] == 2
    assert row["people_count"] == 1
    scans = service.list_zone_scans(ADMIN, zone_id=zone["id"])
    assert len(scans) == 2


def test_duty_and_handover_ack(service: CampService) -> None:
    session, unit = _session(service)
    _staff(service, session["id"], unit["id"], "Вожатый", 3)
    counselor = service.get_actor_for_user(3)
    assert counselor is not None

    shift = service.create_duty_shift(
        ADMIN,
        user_id=3,
        role="counselor",
        starts_at_ms=1_000,
        ends_at_ms=2_000,
    )
    assert shift["user_id"] == 3
    assert len(service.list_duty_shifts(counselor)) == 1

    handover = service.create_handover(
        ADMIN,
        to_user_id=3,
        notes="Night shift notes",
        open_items=["Lock the pool gate", {"child": "Аня", "issue": "medication"}],
    )
    assert handover["acknowledged"] is False
    assert len(handover["open_items"]) == 2
    assert len(service.list_handovers(counselor)) == 1

    acked = service.acknowledge_handover(counselor, handover_id=handover["id"])
    assert acked["acknowledged"] is True


def test_pickup_restriction_and_gate_movement(service: CampService) -> None:
    session, unit = _session(service)
    child = _child(service, session["id"], unit["id"], "Аня")
    auth = service.create_pickup_auth(
        ADMIN,
        person_id=child["id"],
        adult_name="Мама",
        relationship="mother",
        restrictions="Only mother may pick up",
    )
    verified = service.verify_pickup(ADMIN, qr_code=auth["qr_code"])
    assert verified["display_name"] == "Аня"

    with pytest.raises(CampError) as exc:
        service.record_movement(ADMIN, person_id=child["id"], direction="out", qr_code=auth["qr_code"])
    assert exc.value.code == "pickup_restricted"

    out = service.record_movement(
        ADMIN,
        person_id=child["id"],
        direction="out",
        qr_code=auth["qr_code"],
        override_reason="Director approved the mother's ID",
    )
    assert out["direction"] == "out"
    with pytest.raises(CampError) as exc:
        service.record_movement(ADMIN, person_id=child["id"], direction="out")
    assert exc.value.code == "movement_conflict"

    back = service.record_movement(ADMIN, person_id=child["id"], direction="in")
    assert back["direction"] == "in"
    assert len(service.gate_log(ADMIN)) == 2


def test_dietary_list_and_remove(service: CampService) -> None:
    session, unit = _session(service)
    child = _child(service, session["id"], unit["id"], "Аня")
    service.set_dietary(ADMIN, person_id=child["id"], restriction="Без орехов", note="Severe allergy")
    service.set_dietary(ADMIN, person_id=child["id"], restriction="Без лактозы")
    items = service.list_dietary(ADMIN)
    assert len(items) == 2
    service.remove_dietary(ADMIN, person_id=child["id"], restriction="Без лактозы")
    assert [item["restriction"] for item in service.list_dietary(ADMIN)] == ["Без орехов"]


def test_parent_digest_only_for_linked_child(service: CampService) -> None:
    session, unit = _session(service)
    child = _child(service, session["id"], unit["id"], "Аня")
    other = _child(service, session["id"], unit["id"], "Боря", user_id=5)
    parent = service.create_person(
        ADMIN,
        session_id=session["id"],
        user_id=4,
        role="parent",
        display_name="Мама Ани",
    )
    service.link_guardian(
        ADMIN, person_id=child["id"], parent_person_id=parent["id"], relationship="mother"
    )
    service.upsert_digest(
        ADMIN, person_id=child["id"], date="2026-11-13", text="Аня хорошо провела день."
    )
    service.upsert_digest(
        ADMIN, person_id=other["id"], date="2026-11-13", text="Боря хорошо провёл день."
    )
    parent_actor = service.get_actor_for_user(4)
    assert parent_actor is not None
    assert service.list_digests(parent_actor) == []

    sent = service.mark_digest_sent(ADMIN, person_id=child["id"], date="2026-11-13")
    assert sent["sent_at_ms"] is not None
    items = service.list_digests(parent_actor)
    assert len(items) == 1
    assert items[0]["person_id"] == child["id"]
