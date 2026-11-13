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
    db_path = tmp_path / "camp_cycle3.sqlite3"
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
                ("other_parent", "x", "user"),
            ],
        )
    return CampService(db_path)


def _session(service: CampService):
    session = service.create_session(ADMIN, name="Cycle 3 camp", status="active")
    unit = service.create_unit(ADMIN, session_id=session["id"], name="Squad A")
    child = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        role="child",
        age_band="10_13",
        display_name="Аня",
    )
    return session, unit, child


def _parent(service: CampService, session_id: int, user_id: int, name: str):
    return service.create_person(
        ADMIN,
        session_id=session_id,
        user_id=user_id,
        role="parent",
        display_name=name,
    )


def test_kiosk_only_stores_hash_and_revoke_stops_scans(service: CampService) -> None:
    session, _, child = _session(service)
    zone = service.create_zone(ADMIN, name="Main gate", kind="gate")
    created = service.create_kiosk(
        ADMIN, device_id="gate-pi-1", zone_id=zone["id"], scopes="scan"
    )
    token = created["token"]
    assert token.startswith("KIOSK-")
    assert "token_hash" not in created["item"]

    items = service.list_kiosks(ADMIN)
    assert len(items) == 1
    assert "token_hash" not in items[0]
    assert items[0]["active"] is True

    scanned = service.kiosk_scan(kiosk_token=token, badge_code=child["badge_code"])
    assert scanned["person"]["id"] == child["id"]
    assert scanned["scan"]["source"] == "kiosk"

    last = service.list_kiosks(ADMIN)[0]
    assert last["last_seen_ms"] is not None
    assert last["stale"] is False

    service.revoke_kiosk(ADMIN, kiosk_id=created["item"]["id"])
    with pytest.raises(CampError) as exc:
        service.kiosk_scan(kiosk_token=token, person_id=child["id"])
    assert exc.value.code == "kiosk_revoked"


def test_offline_sync_is_idempotent(service: CampService) -> None:
    session, unit, child = _session(service)
    zone = service.create_zone(ADMIN, name="Canteen", kind="checkpoint")
    event = service.create_attendance_event(
        ADMIN, session_id=session["id"], unit_id=unit["id"]
    )
    ops = [
        {
            "op_id": "op-scan-1",
            "kind": "scan",
            "payload": {"zone_id": zone["id"], "person_id": child["id"]},
        },
        {
            "op_id": "op-mark-1",
            "kind": "attendance_mark",
            "payload": {
                "event_id": event["id"],
                "person_id": child["id"],
                "status": "present",
            },
        },
    ]
    first = service.sync_offline(ADMIN, device_id="offline-tablet", operations=ops)
    assert [item["status"] for item in first] == ["accepted", "accepted"]
    assert len(service.list_zone_scans(ADMIN, zone_id=zone["id"])) == 1
    assert service.get_attendance_event(ADMIN, event_id=event["id"])["summary"]["present"] == 1

    replay = service.sync_offline(ADMIN, device_id="offline-tablet", operations=ops)
    assert all(item["replayed"] is True for item in replay)
    assert len(service.list_zone_scans(ADMIN, zone_id=zone["id"])) == 1
    assert service.get_attendance_event(ADMIN, event_id=event["id"])["summary"]["present"] == 1


def test_sync_rejects_unknown_kind(service: CampService) -> None:
    _session(service)
    result = service.sync_offline(
        ADMIN,
        device_id="tablet",
        operations=[{"op_id": "bad-1", "kind": "delete_everything", "payload": {}}],
    )
    assert result[0]["status"] == "rejected"
    assert "Unsupported" in result[0]["error"]


def test_consent_matrix_and_parent_scope(service: CampService) -> None:
    session, _, child = _session(service)
    parent = _parent(service, session["id"], 4, "Мама Ани")
    other_parent = _parent(service, session["id"], 5, "Другой родитель")
    service.link_guardian(
        ADMIN, person_id=child["id"], parent_person_id=parent["id"], relationship="mother"
    )
    parent_actor = service.get_actor_for_user(4)
    assert parent_actor is not None

    saved = service.set_consent(
        parent_actor, person_id=child["id"], kind="parent_digest", granted=True
    )
    assert saved["granted"] == 1
    got = service.get_consents(parent_actor, person_id=child["id"])
    assert got["parent_digest"] is True
    matrix = service.consent_matrix(ADMIN)
    assert matrix[0]["consents"]["parent_digest"] is True

    other_actor = service.get_actor_for_user(5)
    assert other_actor is not None
    with pytest.raises(CampError) as exc:
        service.set_consent(
            other_actor, person_id=child["id"], kind="promo", granted=True
        )
    assert exc.value.code == "guardian_forbidden"


def test_report_csv_html_and_status(service: CampService) -> None:
    session, unit, child = _session(service)
    service.set_dietary(ADMIN, person_id=child["id"], restriction="Без орехов")
    report = service.session_report(ADMIN)
    assert report["session"]["id"] == session["id"]
    assert report["people"]["children"] == 1
    assert report["dietary"]["records"] == 1
    assert report["units"][0]["child_count"] == 1

    csv_body = service.report_csv(ADMIN)
    assert csv_body.startswith("\ufeff")
    assert "dietary,records,1" in csv_body
    html_body = service.report_html(ADMIN)
    assert "Camp report" in html_body
    assert "Cycle 3 camp" in html_body

    status = service.system_status()
    assert status["status"] == "ok"
    assert status["checks"]["db_read"] is True
    assert status["checks"]["db_write"] is True
    assert status["checks"]["db_quick_check"] == "ok"
