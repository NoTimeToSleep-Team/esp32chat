"""Regression suite for the 2026-11-09 deep test round.

Run against a disposable local server. The suite intentionally makes more than
30 `/auth/*` and 240 total requests in one process, so raise only the generic
in-memory buckets for the run; the dedicated registration/room-code/pairing
failure limiters must stay at their defaults:
    LCS_RATE_LIMIT_MAX_REQUESTS=10000 \
    LCS_AUTH_RATE_LIMIT_MAX_REQUESTS=10000 \
    LC_BASE=http://127.0.0.1:18082 LC_TEST_DB=<db path> \
        server/.venv/Scripts/python.exe tests/server/test_security_fixes_2026_11_09d.py
"""

from __future__ import annotations

import os
import random
import sqlite3
import sys

import requests

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18082")
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
    device_id = "web-" + os.urandom(6).hex()
    status, body = req(
        "POST",
        "/auth/register",
        json={
            "login": login,
            "password": "Sec-pass-12345",
            "phone": "+7999" + str(random.randint(1000000, 9999999)),
            "device_id": device_id,
            "client_kind": "web",
        },
    )
    assert status == 200, (status, body)
    return body["session"]["token"], body["user"]["id"], login, device_id


def create_group(token: str, title: str, member_ids: list[int]) -> int:
    status, body = req(
        "POST",
        "/chat/api/chats",
        json={
            "session_token": token,
            "title": title,
            "member_ids": member_ids,
            "chat_type": "group",
        },
    )
    assert status == 200, (status, body)
    return body["chat"]["chat_id"]


def set_role(token: str, chat_id: int, user_id: int, role: str):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/members/{user_id}/role",
        json={"session_token": token, "role": role},
    )


def set_permissions(token: str, chat_id: int, user_id: int, permissions: dict[str, bool]):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/members/{user_id}/permissions",
        json={"session_token": token, "permissions": permissions},
    )


def member_permissions(token: str, chat_id: int, user_id: int):
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/members",
        params={"session_token": token},
    )
    assert status == 200, (status, body)
    for item in body.get("items", []):
        if item.get("user_id") == user_id:
            return item.get("permissions")
    return None


def create_invite(token: str, chat_id: int):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/invites",
        json={"session_token": token},
    )


def send_message(token: str, chat_id: int, text: str):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        json={"session_token": token, "body_text": text},
    )


def delete_message(token: str, chat_id: int, message_id: int):
    return req(
        "DELETE",
        f"/chat/api/chats/{chat_id}/messages/{message_id}",
        json={"session_token": token},
    )


def login_token(login: str, password: str, device_id: str):
    return req(
        "POST",
        "/auth/login",
        json={
            "login": login,
            "password": password,
            "device_id": device_id,
            "client_kind": "web",
        },
    )


def partial_permissions_default_closed() -> None:
    owner, _owner_id, _, _ = register("deep-owner")
    admin, admin_id, _, _ = register("deep-admin")
    chat_id = create_group(owner, "partial permissions", [admin_id])
    status, body = set_role(owner, chat_id, admin_id, "admin")
    assert status == 200, (status, body)

    status, body = set_permissions(owner, chat_id, admin_id, {"restrict_members": False})
    check("partial permissions request accepted", status == 200, (status, body))
    permissions = member_permissions(owner, chat_id, admin_id)
    check(
        "omitted flags default to false",
        isinstance(permissions, dict)
        and all(permissions.get(name) is False for name in PERMISSIONS),
        permissions,
    )
    status, body = create_invite(admin, chat_id)
    check(
        "admin with omitted invite permission cannot create invite",
        status == 403,
        (status, body),
    )

    status, body = set_permissions(owner, chat_id, admin_id, {})
    check("empty permissions request accepted", status == 200, (status, body))
    permissions = member_permissions(owner, chat_id, admin_id)
    check(
        "empty permissions map revokes every flag",
        isinstance(permissions, dict)
        and all(permissions.get(name) is False for name in PERMISSIONS),
        permissions,
    )

    status, body = set_permissions(owner, chat_id, admin_id, {"manage_invites": True})
    check("single granted flag accepted", status == 200, (status, body))
    permissions = member_permissions(owner, chat_id, admin_id)
    check(
        "only the explicitly granted flag is true",
        isinstance(permissions, dict)
        and permissions.get("manage_invites") is True
        and all(permissions.get(name) is False for name in PERMISSIONS if name != "manage_invites"),
        permissions,
    )
    status, body = create_invite(admin, chat_id)
    check(
        "explicit manage_invites flag allows invite",
        status == 200,
        (status, body),
    )


def corrupted_permissions_fail_closed() -> None:
    assert DB_PATH, "LC_TEST_DB is required for the corrupted-permissions test"
    owner, _owner_id, _, _ = register("deep-corrupt-owner")
    admin, admin_id, _, _ = register("deep-corrupt-admin")
    chat_id = create_group(owner, "corrupted permissions", [admin_id])
    status, body = set_role(owner, chat_id, admin_id, "admin")
    assert status == 200, (status, body)

    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.execute(
            "UPDATE chat_members SET permissions = ? WHERE chat_id = ? AND user_id = ?",
            ("{not-json", chat_id, admin_id),
        )
        connection.commit()
    finally:
        connection.close()

    status, body = create_invite(admin, chat_id)
    check(
        "corrupted admin permissions fail closed",
        status == 403,
        (status, body),
    )


def dm_stays_exactly_two_members() -> None:
    a_token, _a_id, _, _ = register("deep-dm-a")
    b_token, b_id, _, _ = register("deep-dm-b")
    status, body = req(
        "POST",
        "/chat/api/dm",
        json={"session_token": a_token, "target_user_id": b_id},
    )
    assert status == 200, (status, body)
    chat_id = body["chat"]["chat_id"]

    status, body = req(
        "POST",
        "/chat/api/dm",
        json={"session_token": b_token, "target_user_id": _a_id},
    )
    check(
        "both participants reuse the same DM",
        status == 200 and body["chat"]["chat_id"] == chat_id,
        (status, body),
    )

    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/leave",
        json={"session_token": a_token},
    )
    check("DM leave accepted", status == 200, (status, body))

    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}/members",
        params={"session_token": b_token},
    )
    check(
        "DM still has exactly two members after leave",
        status == 200 and len(body.get("items", [])) == 2,
        (status, body),
    )

    status, body = req("GET", "/chat/api/chats", params={"session_token": a_token})
    leaver_chat = next(
        (item for item in body.get("items", []) if item.get("chat_id") == chat_id),
        None,
    ) if status == 200 else None
    check(
        "leave archives the DM only for the leaver",
        leaver_chat is not None and leaver_chat.get("is_archived") is True,
        (status, body),
    )

    status, body = req(
        "POST",
        "/chat/api/dm",
        json={"session_token": a_token, "target_user_id": b_id},
    )
    check(
        "reopening the DM reuses the same chat",
        status == 200 and body["chat"]["chat_id"] == chat_id,
        (status, body),
    )
    status, body = req("GET", "/chat/api/chats", params={"session_token": a_token})
    reopened = next(
        (item for item in body.get("items", []) if item.get("chat_id") == chat_id),
        None,
    ) if status == 200 else None
    check(
        "reopened DM is unarchived for the leaver",
        reopened is not None and reopened.get("is_archived") is False,
        (status, body),
    )

    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        json={"session_token": b_token, "body_text": "still here"},
    )
    check("other participant can still send", status == 200, (status, body))


def delete_messages_permission() -> None:
    owner, _owner_id, _, _ = register("deep-del-owner")
    admin, admin_id, _, _ = register("deep-del-admin")
    member, member_id, _, _ = register("deep-del-member")
    chat_id = create_group(owner, "delete permission", [admin_id, member_id])
    status, body = set_role(owner, chat_id, admin_id, "admin")
    assert status == 200, (status, body)

    allowed = {name: False for name in PERMISSIONS}
    allowed["delete_messages"] = True
    status, body = set_permissions(owner, chat_id, admin_id, allowed)
    assert status == 200, (status, body)

    status, body = send_message(member, chat_id, "delete me as admin")
    check("member message created for delete test", status == 200, (status, body))
    message_id = body["message"]["message_id"]
    status, body = delete_message(admin, chat_id, message_id)
    check(
        "admin with delete_messages can delete another user's message",
        status == 200,
        (status, body),
    )

    status, body = set_permissions(owner, chat_id, admin_id, {})
    assert status == 200, (status, body)
    status, body = send_message(member, chat_id, "delete me as owner")
    assert status == 200, (status, body)
    message_id = body["message"]["message_id"]
    status, body = delete_message(admin, chat_id, message_id)
    check(
        "admin without delete_messages cannot delete another user's message",
        status == 403,
        (status, body),
    )
    status, body = delete_message(owner, chat_id, message_id)
    check(
        "chat owner can delete another user's message",
        status == 200,
        (status, body),
    )


def mark_read_ignores_foreign_messages() -> None:
    owner, _owner_id, _, _ = register("deep-read-owner")
    member, member_id, _, _ = register("deep-read-member")
    outsider, outsider_id, _, _ = register("deep-read-outsider")
    chat_id = create_group(owner, "read target", [member_id])
    other_id = create_group(owner, "read foreign", [outsider_id])

    status, body = send_message(owner, chat_id, "local message")
    assert status == 200, (status, body)
    local_message_id = body["message"]["message_id"]
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/read",
        json={"session_token": member, "message_id": local_message_id},
    )
    check("mark-read accepts a message from the same chat", status == 200, (status, body))

    status, body = send_message(outsider, other_id, "foreign message")
    assert status == 200, (status, body)
    foreign_message_id = body["message"]["message_id"]
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/read",
        json={"session_token": member, "message_id": foreign_message_id},
    )
    check("mark-read ignores a message from another chat", status == 200, (status, body))
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}",
        params={"session_token": member},
    )
    view = body.get("view", {}) if status == 200 else {}
    check(
        "foreign mark-read does not advance the read marker",
        view.get("last_read_message_id") == local_message_id,
        view.get("last_read_message_id"),
    )


def private_join_rate_limit() -> None:
    owner, _owner_id, _, _ = register("deep-private-owner")
    intruder, _intruder_id, _, _ = register("deep-private-intruder")
    status, body = req(
        "POST",
        "/chat/api/private",
        json={
            "session_token": owner,
            "title": "rate limited room",
            "room_code": "123456",
        },
    )
    assert status == 200, (status, body)
    chat_id = body["chat"]["chat_id"]

    statuses = []
    for _ in range(12):
        status, body = req(
            "POST",
            f"/chat/api/private/{chat_id}/join",
            json={"session_token": intruder, "room_code": "000000"},
        )
        statuses.append(status)
    check(
        "private room-code guesses are rate limited",
        429 in statuses,
        statuses,
    )


def pairing_request_rate_limit() -> None:
    statuses = []
    for index in range(11):
        status, body = req(
            "POST",
            "/devices/api/pair/request",
            json={
                "device_id": f"deep-pair-{index}-{os.urandom(4).hex()}",
                "device_type": "test",
                "name": "deep pairing",
                "device_secret_hash": "a" * 64,
            },
        )
        statuses.append(status)
    check(
        "anonymous pairing requests are rate limited",
        429 in statuses,
        statuses,
    )


def moderator_user_list_minimized() -> None:
    assert DB_PATH, "LC_TEST_DB is required for the moderator field test"
    moderator, moderator_id, moderator_login, moderator_device = register("deep-mod")
    admin, admin_id, admin_login, admin_device = register("deep-mod-admin")

    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (moderator_id,))
        connection.execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin_id,))
        connection.commit()
    finally:
        connection.close()

    status, body = login_token(moderator_login, "Sec-pass-12345", moderator_device)
    assert status == 200, (status, body)
    moderator_token = body["session"]["token"]
    status, body = login_token(admin_login, "Sec-pass-12345", admin_device)
    assert status == 200, (status, body)
    admin_token = body["session"]["token"]

    status, body = req(
        "GET",
        "/admin/users",
        params={"session_token": moderator_token, "limit": 200},
    )
    check("moderator can list users for moderation", status == 200, (status, body))
    moderator_items = body.get("items", []) if status == 200 else []
    check(
        "moderator list omits phone/device/block reason",
        bool(moderator_items)
        and all(
            "phone" not in item
            and "registration_device_id" not in item
            and "block_reason" not in item
            for item in moderator_items
        ),
        moderator_items[:1],
    )

    status, body = req(
        "GET",
        "/admin/users",
        params={"session_token": admin_token, "limit": 200},
    )
    admin_items = body.get("items", []) if status == 200 else []
    check(
        "platform admin still sees private user fields",
        status == 200
        and bool(admin_items)
        and all("phone" in item for item in admin_items),
        (status, admin_items[:1]),
    )


def registration_enumeration_rate_limit() -> None:
    victim, _victim_id, victim_login, _ = register("deep-enum-victim")
    statuses = []
    for _ in range(12):
        status, body = req(
            "POST",
            "/auth/register",
            json={
                "login": victim_login,
                "password": "Sec-pass-12345",
                "phone": "+7999" + str(random.randint(1000000, 9999999)),
                "device_id": "web-" + os.urandom(6).hex(),
                "client_kind": "web",
            },
        )
        statuses.append(status)
    check(
        "repeated login_taken registration probes are rate limited",
        429 in statuses,
        statuses,
    )


def main() -> None:
    partial_permissions_default_closed()
    corrupted_permissions_fail_closed()
    dm_stays_exactly_two_members()
    delete_messages_permission()
    mark_read_ignores_foreign_messages()
    private_join_rate_limit()
    pairing_request_rate_limit()
    moderator_user_list_minimized()
    registration_enumeration_rate_limit()
    print(f"RESULT: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
