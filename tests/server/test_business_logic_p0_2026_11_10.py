"""Business-logic P0 regression suite for the 2026-11-10 cleanup pass.

Covers the admin cleanup endpoints, full reset semantics, preservation of the
current admin session, and the legacy static-page syntax fixes.

Run against a disposable local server (generic buckets raised for the suite):
    LCS_RATE_LIMIT_MAX_REQUESTS=10000 \
    LCS_AUTH_RATE_LIMIT_MAX_REQUESTS=10000 \
    LC_BASE=http://127.0.0.1:18082 LC_TEST_DB=<db path> \
        server/.venv/Scripts/python.exe tests/server/test_business_logic_p0_2026_11_10.py
"""

from __future__ import annotations

import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18082")
DB_PATH = os.environ.get("LC_TEST_DB", "")
PASSWORD = "P0-cleanup-pass-12345"
STATIC_ROOT = Path(__file__).resolve().parents[2] / "server" / "app" / "static"

passed = 0
failed = 0


def check(name: str, ok: bool, extra: object = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print("  ok  " + name)
    else:
        failed += 1
        print("FAIL  " + name + "  " + str(extra)[:1000])


def req(method: str, path: str, **kwargs):
    response = requests.request(method, BASE + path, timeout=20, **kwargs)
    try:
        body = response.json()
    except Exception:
        body = response.text[:600]
    return response.status_code, body


def register(prefix: str):
    login = prefix + "-" + os.urandom(4).hex()
    device_id = "p0-" + os.urandom(6).hex()
    status, body = req(
        "POST",
        "/auth/register",
        json={
            "login": login,
            "password": PASSWORD,
            "phone": "+7999" + str(random.randint(1000000, 9999999)),
            "device_id": device_id,
            "client_kind": "web",
        },
    )
    assert status == 200, (status, body)
    return login, int(body["user"]["id"]), device_id


def login(login_name: str, device_id: str) -> str:
    status, body = req(
        "POST",
        "/auth/login",
        json={
            "login": login_name,
            "password": PASSWORD,
            "device_id": device_id,
            "client_kind": "web",
        },
    )
    assert status == 200, (status, body)
    return body["session"]["token"]


def set_role(user_id: int, role: str) -> None:
    assert DB_PATH, "LC_TEST_DB is required"
    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        connection.commit()
    finally:
        connection.close()


def db_scalar(sql: str, params: tuple = ()) -> int:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        row = connection.execute(sql, params).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def seed_blacklist(user_id: int) -> str:
    now = int(time.time() * 1000)
    device_id = "p0-device-" + os.urandom(4).hex()
    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.execute(
            """
            INSERT INTO device_blacklist(device_id, reason, blocked_by_user_id, created_at_ms, updated_at_ms)
            VALUES (?, 'p0 seed', ?, ?, ?)
            """,
            (device_id, user_id, now, now),
        )
        connection.commit()
    finally:
        connection.close()
    return device_id


def seed_blog_and_support(user_id: int) -> None:
    now = int(time.time() * 1000)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.execute(
            """
            INSERT INTO blog_posts(title, body_text, author_user_id, published_at_ms, updated_at_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("P0 seed post", "seed", user_id, now, now),
        )
        cursor = connection.execute(
            """
            INSERT INTO support_tickets(user_id, title, status, created_at_ms, updated_at_ms, last_message_at_ms)
            VALUES (?, ?, 'open', ?, ?, ?)
            """,
            (user_id, "P0 seed ticket", now, now, now),
        )
        connection.execute(
            """
            INSERT INTO support_messages(ticket_id, author_user_id, body_text, created_at_ms)
            VALUES (?, ?, ?, ?)
            """,
            (int(cursor.lastrowid), user_id, "seed", now),
        )
        connection.commit()
    finally:
        connection.close()


def cleanup_endpoint_paths_are_current() -> None:
    response = requests.get(BASE + "/static/admin.html", timeout=20)
    status, text = response.status_code, response.text
    check("admin page loads", status == 200, status)
    if status == 200:
        check(
            "cleanup UI uses delete-all-chats",
            '["delete-all-chats"' in text,
            "missing correct route",
        )
        check(
            "cleanup UI uses delete-all-users",
            '["delete-all-users"' in text,
            "missing correct route",
        )
        check(
            "cleanup UI no longer uses delete-chats",
            '["delete-chats"' not in text,
            "old route still present",
        )
        check(
            "full reset asks for typed confirmation",
            "Введите RESET" in text,
            "typed confirmation missing",
        )


def legacy_static_scripts_parse() -> None:
    node = shutil.which("node")
    check("node available for static syntax check", bool(node), "node not found; skipped")
    if not node:
        return
    for relative in ("devices/devices.js", "rfid/rfid.js"):
        path = STATIC_ROOT / relative
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        check(
            f"{relative} parses",
            result.returncode == 0,
            (result.returncode, (result.stderr or result.stdout)[-800:]),
        )


def full_reset_behavior() -> None:
    owner_login, owner_id, owner_device = register("p0-owner")
    other_login, other_id, other_device = register("p0-other-admin")
    member_login, member_id, member_device = register("p0-member")
    second_member_login, second_member_id, _ = register("p0-second-member")
    set_role(owner_id, "admin")
    set_role(other_id, "admin")
    owner_token = login(owner_login, owner_device)
    other_token = login(other_login, other_device)
    member_token = login(member_login, member_device)

    status, body = req(
        "POST",
        "/chat/api/chats",
        json={
            "session_token": owner_token,
            "title": "P0 full reset chat",
            "member_ids": [member_id],
            "chat_type": "group",
        },
    )
    assert status == 200, (status, body)
    chat_id = int(body["chat"]["chat_id"])
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        json={"session_token": member_token, "body_text": "P0 reset message"},
    )
    assert status == 200, (status, body)
    seed_blog_and_support(member_id)
    blacklist_device = seed_blacklist(member_id)

    status, body = req(
        "POST",
        "/chat/api/admin/full-reset",
        json={"session_token": owner_token, "confirm": True},
    )
    check("full reset requires the typed phrase on the server", status == 400, (status, body))

    status, body = req(
        "POST",
        "/chat/api/admin/full-reset",
        json={"session_token": owner_token, "confirm": True, "confirm_phrase": "RESET"},
    )
    check("full reset accepted", status == 200, (status, body))
    if status == 200:
        check("full reset returns deleted_count", isinstance(body.get("deleted_count"), int), body)
        check("full reset reports cleared blog", body.get("blog_deleted", 0) >= 1, body)
        check("full reset reports cleared support", body.get("support_deleted", 0) >= 1, body)
        check("full reset reports deleted non-admin users", body.get("users_deleted", 0) >= 2, body)

    check(
        "current admin session survives full reset",
        req(
            "GET",
            "/admin/users",
            params={"session_token": owner_token, "limit": 200},
        )[0]
        == 200,
    )
    check(
        "other admin session is revoked by full reset",
        req(
            "GET",
            "/admin/users",
            params={"session_token": other_token, "limit": 200},
        )[0]
        == 401,
    )
    check("regular users are removed", db_scalar("SELECT COUNT(*) FROM users WHERE role != 'admin'") == 0)
    check("blog is cleared", db_scalar("SELECT COUNT(*) FROM blog_posts") == 0)
    check("support tickets are cleared", db_scalar("SELECT COUNT(*) FROM support_tickets") == 0)
    check("common chat survives full reset", db_scalar("SELECT COUNT(*) FROM chats WHERE kind = 'common'") == 1)
    check(
        "device blacklist is reassigned to the acting admin",
        db_scalar(
            "SELECT blocked_by_user_id FROM device_blacklist WHERE device_id = ?",
            (blacklist_device,),
        )
        == owner_id,
    )
    check("current admin session row remains", db_scalar("SELECT COUNT(*) FROM sessions WHERE id = ?", (owner_token,)) == 1)
    check("other admin user remains", db_scalar("SELECT COUNT(*) FROM users WHERE id = ?", (other_id,)) == 1)

    return owner_login, owner_id, owner_device, other_login, other_id, other_device


def delete_all_users_preserves_admins() -> None:
    admin_login, admin_id, admin_device = register("p0-del-admin")
    second_admin_login, second_admin_id, second_admin_device = register("p0-del-admin2")
    member_login, member_id, member_device = register("p0-del-member")
    other_login, other_id, other_device = register("p0-del-member2")
    set_role(admin_id, "admin")
    set_role(second_admin_id, "admin")
    admin_token = login(admin_login, admin_device)
    second_admin_token = login(second_admin_login, second_admin_device)
    blacklist_device = seed_blacklist(member_id)

    status, body = req(
        "POST",
        "/chat/api/admin/delete-all-users",
        json={"session_token": admin_token},
    )
    check("delete-all-users accepted", status == 200, (status, body))
    check("delete-all-users reports a count", isinstance(body.get("deleted_count"), int), body)
    check(
        "other admin user survives delete-all-users",
        db_scalar("SELECT COUNT(*) FROM users WHERE id = ?", (second_admin_id,)) == 1,
    )
    check(
        "other admin session survives delete-all-users",
        req(
            "GET",
            "/admin/users",
            params={"session_token": second_admin_token, "limit": 200},
        )[0]
        == 200,
    )
    check(
        "regular users are removed by delete-all-users",
        db_scalar("SELECT COUNT(*) FROM users WHERE id IN (?, ?)", (member_id, other_id)) == 0,
    )
    check(
        "device blacklist survives delete-all-users under the acting admin",
        db_scalar(
            "SELECT blocked_by_user_id FROM device_blacklist WHERE device_id = ?",
            (blacklist_device,),
        )
        == admin_id,
    )

    status, body = req(
        "POST",
        f"/chat/api/chats",
        json={
            "session_token": admin_token,
            "title": "P0 delete all chats",
            "member_ids": [second_admin_id],
            "chat_type": "group",
        },
    )
    assert status == 200, (status, body)
    chat_id = int(body["chat"]["chat_id"])
    status, body = req(
        "POST",
        "/chat/api/admin/delete-all-chats",
        json={"session_token": admin_token},
    )
    check("delete-all-chats accepted", status == 200, (status, body))
    check("delete-all-chats reports a count", isinstance(body.get("deleted_count"), int), body)
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}",
        params={"session_token": admin_token},
    )
    check("delete-all-chats removes the created chat", status in (403, 404), (status, body))


def main() -> None:
    if not DB_PATH:
        print("LC_TEST_DB is required", file=sys.stderr)
        sys.exit(2)
    cleanup_endpoint_paths_are_current()
    legacy_static_scripts_parse()
    full_reset_behavior()
    delete_all_users_preserves_admins()
    print(f"RESULT: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
