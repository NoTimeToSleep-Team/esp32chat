from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.camp.service import CampError, CampService
from app.config import load_settings
from app.db.migrate import apply_sql_migrations


ADMIN = {"user_id": 1, "camp_person_id": None, "role": "director", "session_id": None, "unit_id": None, "display_name": "Director", "age_band": "adult"}


@pytest.fixture()
def service(tmp_path: Path) -> CampService:
    db_path = tmp_path / "camp.sqlite3"
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
                ("counselor2", "x", "user"),
            ],
        )
    return CampService(db_path)


def _session(service: CampService) -> tuple[dict, dict]:
    session = service.create_session(ADMIN, name="Лето 2026", status="active")
    unit = service.create_unit(ADMIN, session_id=session["id"], name="Отряд 1")
    return session, unit


def test_migration_seeds_playbooks(service: CampService) -> None:
    with sqlite3.connect(service._db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM camp_alert_playbooks").fetchone()[0]
        settings = connection.execute("SELECT COUNT(*) FROM camp_settings").fetchone()[0]
    assert count == 5
    assert settings == 0


def test_import_preview_commit_transfer_and_undo(service: CampService) -> None:
    session, unit = _session(service)
    rows = [
        {"display_name": "Аня", "birth_date": "2013-05-01", "unit_name": "Отряд 1", "room": "12"},
        {"display_name": "Боря", "age_band": "10_13", "unit_name": "Отряд 1"},
    ]
    preview = service.import_preview(rows, session_id=session["id"])
    assert preview["status"] == "ok"
    assert preview["summary"]["rows"] == 2

    committed = service.import_commit(ADMIN, session_id=session["id"], rows=rows)
    assert committed["count"] == 2
    people = service.list_people(ADMIN, session_id=session["id"])
    assert {person["display_name"] for person in people} == {"Аня", "Боря"}
    assert all(person["badge_code"].startswith("CAMP-") for person in people)

    anya = next(person for person in people if person["display_name"] == "Аня")
    staff_unit = service.create_unit(ADMIN, session_id=session["id"], name="Staff", kind="staff")
    moved = service.transfer_person(ADMIN, person_id=anya["id"], unit_id=staff_unit["id"])
    assert moved["unit_id"] == staff_unit["id"]

    undone = service.undo_import(ADMIN, batch_id=committed["batch_id"])
    assert undone["deleted"] == 2
    assert service.list_people(ADMIN, session_id=session["id"]) == []


def test_import_duplicate_is_blocked(service: CampService) -> None:
    session, _ = _session(service)
    rows = [
        {"display_name": "Аня", "birth_date": "2013-05-01", "unit_name": "Отряд 1"},
        {"display_name": "Аня", "birth_date": "2013-05-01", "unit_name": "Отряд 1"},
    ]
    preview = service.import_preview(rows, session_id=session["id"])
    assert preview["status"] == "needs_fix"
    assert preview["duplicates"]
    with pytest.raises(CampError) as exc:
        service.import_commit(ADMIN, session_id=session["id"], rows=rows)
    assert exc.value.code == "import_has_errors"


def test_request_queue_claim_close_and_roles(service: CampService) -> None:
    session, unit = _session(service)
    child = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        user_id=2,
        role="child",
        age_band="10_13",
        display_name="Аня",
    )
    counselor = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        user_id=3,
        role="counselor",
        display_name="Вожатый",
    )
    counselor2 = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        user_id=4,
        role="counselor",
        display_name="Вожатый 2",
    )
    child_actor = service.get_actor_for_user(2)
    counselor_actor = service.get_actor_for_user(3)
    counselor2_actor = service.get_actor_for_user(4)
    assert child_actor and child_actor["role"] == "child"
    assert counselor_actor and counselor_actor["role"] == "counselor"
    assert counselor2_actor

    request = service.create_request(child_actor, kind="call_counselor", note="Плохо себя чувствую")
    assert request["status"] == "open"
    assert service.list_requests(counselor_actor)[0]["child_name"] == "Аня"

    claimed = service.claim_request(counselor_actor, int(request["id"]))
    assert claimed["status"] == "claimed"
    with pytest.raises(CampError) as exc:
        service.claim_request(counselor2_actor, int(request["id"]))
    assert exc.value.code == "request_already_claimed"

    closed = service.close_request(counselor_actor, int(request["id"]), note="Проверили")
    assert closed["status"] == "closed"
    assert "Проверили" in closed["note"]


def test_merge_people_keeps_target(service: CampService) -> None:
    session, unit = _session(service)
    target = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        role="child",
        age_band="10_13",
        display_name="Аня",
    )
    source = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        role="child",
        age_band="10_13",
        display_name="Анна",
    )
    merged = service.merge_people(ADMIN, source_id=source["id"], target_id=target["id"])
    assert merged["id"] == target["id"]
    with pytest.raises(CampError):
        service.get_person(ADMIN, source["id"])


def test_policy_check_uses_session_settings(service: CampService) -> None:
    session, unit = _session(service)
    child = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        role="child",
        age_band="10_13",
        display_name="Аня",
    )
    counselor = service.create_person(
        ADMIN,
        session_id=session["id"],
        unit_id=unit["id"],
        role="counselor",
        display_name="Вожатый",
    )
    actor = service.get_actor_for_user(counselor["user_id"]) if counselor["user_id"] else None
    # create_person above has no linked user; build an actor from the row.
    actor = {
        "user_id": 3,
        "camp_person_id": counselor["id"],
        "role": "counselor",
        "session_id": session["id"],
        "unit_id": unit["id"],
        "display_name": "Вожатый",
        "age_band": "adult",
    }
    result = service.policy_check(actor, kind="direct_message", target_person_id=child["id"])
    assert result["allowed"] is False
    assert result["code"] == "adult_child_dm_blocked"


def test_settings_defaults_and_update(service: CampService) -> None:
    session, _ = _session(service)
    settings = service.get_settings(ADMIN, session_id=session["id"])
    assert settings["quiet_start_minutes"] == 1290
    assert settings["quiet_end_minutes"] == 450
    updated = service.update_settings(
        ADMIN,
        session_id=session["id"],
        quiet_start_minutes=22 * 60,
        allow_child_dm=True,
    )
    assert updated["quiet_start_minutes"] == 1320
    assert updated["allow_child_dm"] == 1


def test_camp_edition_config() -> None:
    assert load_settings({"LCS_PROFILE": "test", "LCS_RELOAD": "false"}).edition == "camp"
    assert (
        load_settings(
            {"LCS_PROFILE": "test", "LCS_RELOAD": "false", "LCS_EDITION": "core"}
        ).edition
        == "core"
    )
