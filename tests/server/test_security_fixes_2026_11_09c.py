"""Integration regressions for the third 2026-11-09 pentest report.

Run against a disposable local server started with
``LCS_DEBUG_TRACE_ENABLED=1``:
    LC_BASE=http://127.0.0.1:18081 LC_TEST_DB=<db path> python tests/server/test_security_fixes_2026_11_09c.py
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import random
import sqlite3
import time

import requests

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18081")
DB_PATH = os.environ.get("LC_TEST_DB", "")

PERMISSIONS = (
    "change_info",
    "delete_messages",
    "invite_users",
    "pin_messages",
    "manage_invites",
    "restrict_members",
)

passed = 0
failed = 0


def check(name, ok, extra=""):
    global passed, failed
    if ok:
        passed += 1
        print("  ok  " + name)
    else:
        failed += 1
        print("FAIL  " + name + "  " + str(extra)[:1000])


def req(method, path, **kwargs):
    response = requests.request(method, BASE + path, timeout=20, **kwargs)
    try:
        body = response.json()
    except Exception:
        body = response.text[:600]
    return response.status_code, body


def detail_code(body):
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict):
            return detail.get("code")
    return None


def db():
    if not DB_PATH:
        raise RuntimeError("LC_TEST_DB is required")
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def set_mode(mode):
    with db() as connection:
        connection.execute(
            "UPDATE mode_state SET access_mode = ? WHERE id = 1",
            (mode,),
        )
        connection.commit()


def register(prefix, *, device_id=None):
    login = prefix + "-" + os.urandom(4).hex()
    used_device = device_id or "web-" + os.urandom(6).hex()
    status, body = req(
        "POST",
        "/auth/register",
        json={
            "login": login,
            "password": "Sec-pass-12345",
            "phone": "+7999" + str(random.randint(1000000, 9999999)),
            "device_id": used_device,
            "client_kind": "web",
        },
    )
    assert status == 200, (status, body)
    return body["session"]["token"], body["user"]["id"], login, used_device


def create_group(token, title, member_ids, *, is_public=False):
    status, body = req(
        "POST",
        "/chat/api/chats",
        json={
            "session_token": token,
            "title": title,
            "member_ids": member_ids,
            "chat_type": "group",
            "is_public": is_public,
            "username": "s3" + os.urandom(6).hex(),
        },
    )
    assert status == 200, (status, body)
    return body["chat"]["chat_id"]


def set_role(token, chat_id, user_id, role):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/members/{user_id}/role",
        json={"session_token": token, "role": role},
    )


def set_permissions(token, chat_id, user_id, permissions):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/members/{user_id}/permissions",
        json={"session_token": token, "permissions": permissions},
    )


def create_invite(token, chat_id, **extra):
    payload = {"session_token": token}
    payload.update(extra)
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/invites",
        json=payload,
    )


def join_by_code(token, code):
    return req(
        "POST",
        "/chat/api/join",
        json={"session_token": token, "code": code},
    )


def restricted_permission_checks():
    owner, owner_id, _, _ = register("s3-owner")
    admin, admin_id, _, _ = register("s3-admin")
    member, member_id, _, _ = register("s3-member")
    outsider, outsider_id, _, _ = register("s3-outsider")

    chat_id = create_group(owner, "restricted admin", [admin_id, member_id])
    status, body = set_role(owner, chat_id, admin_id, "admin")
    check("F-01 promote admin", status == 200, (status, body))

    all_false = {name: False for name in PERMISSIONS}
    status, body = set_permissions(owner, chat_id, admin_id, all_false)
    check("F-01 owner can clear admin flags", status == 200, (status, body))

    status, body = create_invite(admin, chat_id)
    check(
        "F-01 restricted admin cannot create invite",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/invites",
        params={"session_token": admin},
    )
    check(
        "F-01 restricted admin cannot list invites",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = set_role(admin, chat_id, member_id, "admin")
    check(
        "F-01 restricted admin cannot promote members",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "DELETE",
        f"/chat/api/chats/{chat_id}/members/{member_id}",
        json={"session_token": admin},
    )
    check(
        "F-01 restricted admin cannot remove members",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/avatar",
        json={
            "session_token": admin,
            "image_base64": "aGVsbG8=",
            "image_mime_type": "image/png",
        },
    )
    check(
        "F-01 restricted admin cannot change chat photo",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/avatar/remove",
        json={"session_token": admin},
    )
    check(
        "F-01 restricted admin cannot clear chat photo",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/requests",
        params={"session_token": admin},
    )
    check(
        "F-01 restricted admin cannot list join requests",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/requests/{outsider_id}",
        json={"session_token": admin, "approve": True},
    )
    check(
        "F-01 restricted admin cannot decide join requests",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )

    only_restrict = {name: False for name in PERMISSIONS}
    only_restrict["restrict_members"] = True
    status, body = set_permissions(owner, chat_id, admin_id, only_restrict)
    check("F-01 owner can grant only restrict_members", status == 200, (status, body))
    status, body = set_role(admin, chat_id, member_id, "admin")
    check(
        "F-01 non-owner cannot appoint a full admin",
        status == 403 and detail_code(body) == "owner_only",
        (status, body),
    )

    all_true = {name: True for name in PERMISSIONS}
    status, body = set_permissions(owner, chat_id, admin_id, all_true)
    check("F-01 owner can restore admin flags", status == 200, (status, body))
    status, body = set_permissions(admin, chat_id, admin_id, all_false)
    check(
        "F-01 admin cannot change own permissions",
        status == 403 and detail_code(body) == "self_permission_change",
        (status, body),
    )

    # A demoted admin must not leave a persistent invite behind.
    status, body = create_invite(admin, chat_id)
    check("F-01 admin can create invite while allowed", status == 200, (status, body))
    code = body["invite"]["code"] if status == 200 else ""
    status, body = set_role(owner, chat_id, admin_id, "member")
    check("F-01 owner can demote admin", status == 200, (status, body))
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/invites",
        params={"session_token": owner},
    )
    check(
        "F-01 demotion revokes admin invites",
        status == 200 and body.get("count") == 0,
        (status, body),
    )
    status, body = join_by_code(outsider, code)
    check(
        "F-01 revoked invite cannot be used",
        status == 404 and detail_code(body) == "invite_not_found",
        (status, body),
    )

    # The same must hold when an admin is kicked rather than demoted.
    status, body = set_role(owner, chat_id, admin_id, "admin")
    check("F-01 re-promote admin", status == 200, (status, body))
    status, body = create_invite(admin, chat_id)
    check("F-01 admin can create second invite", status == 200, (status, body))
    code = body["invite"]["code"] if status == 200 else ""
    status, body = req(
        "DELETE",
        f"/chat/api/chats/{chat_id}/members/{admin_id}",
        json={"session_token": owner},
    )
    check("F-01 owner can kick admin", status == 200, (status, body))
    status, body = join_by_code(outsider, code)
    check(
        "F-01 kicked admin invite is revoked",
        status == 404 and detail_code(body) == "invite_not_found",
        (status, body),
    )


def invite_race_check():
    owner, _, _, _ = register("s3-race-owner")
    seed, seed_id, _, _ = register("s3-race-seed")
    joiners = [register(f"s3-race-{index}") for index in range(5)]
    chat_id = create_group(owner, "invite race", [seed_id])
    status, body = create_invite(owner, chat_id, max_uses=1)
    check("F-07 limited invite created", status == 200, (status, body))
    code = body["invite"]["code"] if status == 200 else ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda item: join_by_code(item[0], code), joiners))

    joined = [item for item in results if item[0] == 200]
    exhausted = [item for item in results if item[0] == 410]
    check(
        "F-07 max_uses is enforced atomically",
        len(joined) == 1 and len(exhausted) == 4,
        [(status, detail_code(body)) for status, body in results],
    )
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/members",
        params={"session_token": owner},
    )
    check(
        "F-07 only one member joined",
        status == 200 and body.get("count") == 3,
        (status, body),
    )


def poll_limits_check():
    owner, owner_id, _, _ = register("s3-poll-owner")
    member, member_id, _, _ = register("s3-poll-member")
    chat_id = create_group(owner, "poll limits", [member_id])

    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/polls",
        json={
            "session_token": owner,
            "question": "large option",
            "options": ["A" * 5000, "B"],
        },
    )
    check(
        "F-03 oversized poll option rejected",
        status == 422 and detail_code(body) == "poll_option_too_long",
        (status, body),
    )

    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/polls",
        json={
            "session_token": owner,
            "question": "bounded poll",
            "options": ["A" * 300, "B" * 300],
        },
    )
    check("F-03 bounded poll accepted", status == 200, (status, body))
    message_id = body["message"]["message_id"] if status == 200 else 0
    poll_id = body["message"]["poll"]["poll_id"] if status == 200 else 0

    # Simulate a legacy oversized row: reads must clamp it, not serialize MBs.
    huge_options = json.dumps(["X" * 100_000 for _ in range(10)])
    with db() as connection:
        connection.execute(
            "UPDATE chat_polls SET question = ?, options_json = ? WHERE id = ?",
            ("Q" * 20_000, huge_options, poll_id),
        )
        connection.commit()

    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/messages",
        params={"session_token": owner, "limit": 50},
    )
    found = None
    if status == 200:
        for item in body.get("items", []):
            if item.get("message_id") == message_id:
                found = item
                break
    poll = (found or {}).get("poll") or {}
    check(
        "F-03 legacy oversized poll is clamped on read",
        status == 200
        and len(poll.get("question", "")) <= 300
        and all(len(option.get("text", "")) <= 300 for option in poll.get("options", [])),
        (status, poll.get("question"), poll.get("options")),
    )
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/messages",
        params={"session_token": owner, "limit": 500},
    )
    check("F-03 message page limit is capped", status == 422, (status, body))


def debug_trace_check():
    token, _, _, _ = register("s3-debug")
    with db() as connection:
        before = int(connection.execute("SELECT COUNT(*) FROM debug_events").fetchone()[0])

    for index in range(20):
        status, _ = req(
            "GET",
            f"/missing-{index}",
            headers={"X-Debug-Trace": "trace-missing-" + str(index)},
        )
        assert status == 404

    with db() as connection:
        after_missing = int(connection.execute("SELECT COUNT(*) FROM debug_events").fetchone()[0])
    check(
        "F-02 unauthenticated 404 probes are not logged",
        after_missing == before,
        (before, after_missing),
    )

    status, body = req(
        "GET",
        "/chat/api/chats",
        headers={
            "X-Session-Token": token,
            "X-Debug-Trace": "trace-authenticated",
        },
    )
    with db() as connection:
        after_auth = int(connection.execute("SELECT COUNT(*) FROM debug_events").fetchone()[0])
    check(
        "F-02 authenticated trace is logged",
        status == 200 and after_auth > after_missing,
        (status, before, after_missing, after_auth, body),
    )


def device_binding_check():
    device_id = "shared-" + os.urandom(6).hex()
    token, user_id, login, _ = register("s3-device-a", device_id=device_id)

    status, body = req(
        "POST",
        "/auth/register",
        json={
            "login": "s3-device-b-" + os.urandom(4).hex(),
            "password": "Sec-pass-12345",
            "phone": "+7999" + str(random.randint(1000000, 9999999)),
            "device_id": device_id,
            "client_kind": "web",
        },
    )
    check(
        "F-06 one device cannot register two accounts",
        status == 409 and detail_code(body) == "device_already_registered",
        (status, body),
    )

    with db() as connection:
        row = connection.execute(
            "SELECT device_id FROM sessions WHERE id = ?",
            (token,),
        ).fetchone()
    check(
        "F-06 web session is bound to the registration device",
        row is not None and str(row["device_id"] or "") == device_id,
        row["device_id"] if row is not None else None,
    )

    status, body = req(
        "POST",
        "/auth/login",
        json={
            "login": login,
            "password": "Sec-pass-12345",
            "device_id": "rotated-" + os.urandom(6).hex(),
            "client_kind": "web",
        },
    )
    second_token = (
        body.get("session", {}).get("token") if isinstance(body, dict) else None
    )
    with db() as connection:
        row = connection.execute(
            "SELECT device_id FROM sessions WHERE id = ?",
            (second_token,),
        ).fetchone()
    check(
        "F-06 login with a changed local id keeps the canonical binding",
        status == 200
        and row is not None
        and str(row["device_id"] or "") == device_id,
        (status, body, row["device_id"] if row is not None else None),
    )

    now_ms = int(time.time() * 1000)
    with db() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO device_blacklist(device_id, reason, blocked_by_user_id, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?)",
            (device_id, "regression", user_id, now_ms, now_ms),
        )
        connection.commit()
    status, body = req(
        "GET",
        "/chat/api/chats",
        headers={"X-Session-Token": token},
    )
    check(
        "F-06 blacklisted registration device kills the session",
        status == 403 and detail_code(body) == "device_blacklisted",
        (status, body),
    )


def enumeration_check():
    viewer, _, _, _ = register("s3-enum-viewer")
    target, target_id, target_login, _ = register("s3-enum-target")
    with db() as connection:
        connection.execute(
            "UPDATE users SET role = 'moderator' WHERE id = ?",
            (target_id,),
        )
        connection.commit()

    status, body = req(
        "GET",
        "/chat/api/users/search",
        params={"session_token": viewer, "q": target_login},
    )
    items = (body or {}).get("items") or [] if isinstance(body, dict) else []
    match = next((item for item in items if item.get("user_id") == target_id), None)
    check(
        "F-13 regular user search hides platform roles",
        status == 200 and match is not None and match.get("role") == "user" and "status" not in match,
        (status, match),
    )

    status, body = req(
        "GET",
        f"/account/api/profile/{target_id}",
        params={"session_token": viewer},
    )
    profile = (body or {}).get("profile") or {}
    check(
        "F-13 foreign profile hides role and status",
        status == 200 and profile.get("role") == "user" and profile.get("status") == "active",
        (status, profile),
    )

    status, body = req(
        "GET",
        "/chat/api/users/search",
        params={"session_token": target, "q": target_login},
    )
    items = (body or {}).get("items") or [] if isinstance(body, dict) else []
    match = next((item for item in items if item.get("user_id") == target_id), None)
    check(
        "F-13 privileged search still sees roles",
        status == 200 and match is not None and match.get("role") == "moderator",
        (status, match),
    )


def main():
    set_mode("open")
    restricted_permission_checks()
    invite_race_check()
    poll_limits_check()
    debug_trace_check()
    device_binding_check()
    enumeration_check()
    print(f"RESULT: {passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
