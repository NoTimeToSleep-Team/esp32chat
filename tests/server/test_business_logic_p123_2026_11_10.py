"""Business-logic P1/P2/P3 regressions for the 2026-11-10 logic review.

Covers private-room publishing, poll auto-moderation, quota consistency,
duplicate poll options, common-chat leave, and stale pins.

Run against a disposable server:
    LCS_RATE_LIMIT_MAX_REQUESTS=10000 \
    LCS_AUTH_RATE_LIMIT_MAX_REQUESTS=10000 \
    LC_BASE=http://127.0.0.1:18082 LC_TEST_DB=<db path> \
        server/.venv/Scripts/python.exe tests/server/test_business_logic_p123_2026_11_10.py
"""

from __future__ import annotations

import os
import random
import sqlite3
import sys
import time

import requests

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18082")
DB_PATH = os.environ.get("LC_TEST_DB", "")
PASSWORD = "P123-logic-pass-12345"

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
    device_id = "p123-" + os.urandom(6).hex()
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


def db_exec(sql: str, params: tuple = ()) -> None:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def create_group(token: str, title: str, member_ids: list[int], **extra) -> int:
    payload = {
        "session_token": token,
        "title": title,
        "member_ids": member_ids,
        "chat_type": "group",
        **extra,
    }
    status, body = req("POST", "/chat/api/chats", json=payload)
    assert status == 200, (status, body)
    return int(body["chat"]["chat_id"])


def send_message(token: str, chat_id: int, text: str):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        json={"session_token": token, "body_text": text},
    )


def create_poll(token: str, chat_id: int, question: str, options: list[str]):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/polls",
        json={
            "session_token": token,
            "question": question,
            "options": options,
        },
    )


def private_room_cannot_be_published() -> None:
    owner_login, owner_id, owner_device = register("p123-owner")
    outsider_login, outsider_id, outsider_device = register("p123-outsider")
    owner_token = login(owner_login, owner_device)
    outsider_token = login(outsider_login, outsider_device)

    status, body = req(
        "POST",
        "/chat/api/private",
        json={
            "session_token": owner_token,
            "title": "P1 private room",
            "room_code": "654321",
        },
    )
    check("private room created", status == 200, (status, body))
    chat_id = int(body["chat"]["chat_id"])
    status, body = send_message(owner_token, chat_id, "private history")
    check("owner posts in private room", status == 200, (status, body))
    check(
        "outsider cannot read a coded room",
        req(
            "GET",
            f"/chat/api/chats/{chat_id}/messages",
            params={"session_token": outsider_token},
        )[0]
        == 403,
    )

    status, body = req(
        "PATCH",
        f"/chat/api/chats/{chat_id}",
        json={
            "session_token": owner_token,
            "is_public": True,
            "username": "p123_private_public_" + os.urandom(3).hex(),
        },
    )
    check(
        "coded room cannot be published",
        status == 409 and (body.get("detail") or {}).get("code") == "private_room_cannot_be_public",
        (status, body),
    )
    check(
        "outsider still cannot read after rejected publish",
        req(
            "GET",
            f"/chat/api/chats/{chat_id}/messages",
            params={"session_token": outsider_token},
        )[0]
        == 403,
    )
    db_exec("UPDATE chats SET is_public = 1 WHERE id = ?", (chat_id,))
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}",
        params={"session_token": owner_token},
    )
    check(
        "legacy published private room is normalized on read",
        status == 200 and body.get("chat", {}).get("is_public") is False,
        (status, body),
    )

    # A public chat converted to a private room must drop its public link.
    public_chat = create_group(
        owner_token,
        "P1 public to private",
        [outsider_id],
        is_public=True,
        username="p123_public_" + os.urandom(3).hex(),
    )
    status, body = req(
        "POST",
        f"/chat/api/private/{public_chat}/config",
        json={
            "session_token": owner_token,
            "is_private": True,
            "room_code": "123456",
        },
    )
    check("public chat can be converted to private room", status == 200, (status, body))
    status, body = req(
        "GET",
        f"/chat/api/chats/{public_chat}",
        params={"session_token": owner_token},
    )
    check(
        "converted room is no longer public",
        status == 200 and body.get("chat", {}).get("is_public") is False,
        (status, body),
    )
    response = requests.get(BASE + "/static/app.js", timeout=20)
    check(
        "UI hides publish controls for private rooms",
        response.status_code == 200
        and "const canPublish = !chat.is_private && !chat.has_room_code" in response.text,
        response.status_code,
    )


def automod_scans_polls() -> None:
    admin_login, admin_id, admin_device = register("p123-admin")
    user_login, user_id, user_device = register("p123-automod-user")
    set_role(admin_id, "admin")
    admin_token = login(admin_login, admin_device)
    user_token = login(user_login, user_device)
    word = "p123bad" + os.urandom(3).hex()

    status, body = req(
        "POST",
        "/reports/api/auto-moderation",
        json={"session_token": admin_token, "enabled": True, "extra_words": word, "whitelist": ""},
    )
    check("automod settings updated", status == 200, (status, body))
    # The service caches settings for five seconds.
    time.sleep(5.2)

    chat_id = create_group(admin_token, "P1 poll automod", [user_id])
    status, body = create_poll(user_token, chat_id, word + " question", ["clean", "also clean"])
    check("poll with bad question still gets a message id", status == 200, (status, body))
    bad_question_message = int(body.get("message", {}).get("message_id", 0)) if status == 200 else 0
    status, body = create_poll(user_token, chat_id, "clean question", [word + " option", "clean"])
    check("poll with bad option is accepted with a message id", status == 200, (status, body))
    bad_option_message = int(body.get("message", {}).get("message_id", 0)) if status == 200 else 0
    check(
        "poll question is auto-moderated",
        db_scalar("SELECT COUNT(*) FROM user_reports WHERE message_id = ?", (bad_question_message,)) >= 1,
        bad_question_message,
    )
    check(
        "poll option is auto-moderated",
        db_scalar("SELECT COUNT(*) FROM user_reports WHERE message_id = ?", (bad_option_message,)) >= 1,
        bad_option_message,
    )


def quota_counts_match() -> None:
    owner_login, owner_id, owner_device = register("p123-quota-owner")
    member_login, member_id, member_device = register("p123-quota-member")
    owner_token = login(owner_login, owner_device)

    for index in range(5):
        create_group(owner_token, f"P123 quota {index}", [member_id])
    status, body = req(
        "POST",
        "/chat/api/dm",
        json={"session_token": owner_token, "target_user_id": member_id},
    )
    check("DM created alongside quota groups", status == 200, (status, body))

    status, body = req(
        "GET",
        "/account/api/limits",
        params={"session_token": owner_token},
    )
    limits = (body.get("limits") or {}) if isinstance(body, dict) else {}
    check("limits endpoint responds", status == 200, (status, body))
    check("quota count excludes DMs", limits.get("current_custom_chats") == 5, limits)
    check("quota maximum is five", limits.get("max_custom_chats") == 5, limits)
    check("quota remaining is zero", limits.get("remaining_custom_chats") == 0, limits)


def pending_requests_hidden_from_outsiders() -> None:
    owner_login, owner_id, owner_device = register("p123-pending-owner")
    member_login, member_id, member_device = register("p123-pending-member")
    outsider_login, outsider_id, outsider_device = register("p123-pending-outsider")
    owner_token = login(owner_login, owner_device)
    outsider_token = login(outsider_login, outsider_device)
    chat_id = create_group(
        owner_token,
        "P123 pending requests",
        [member_id],
        is_public=True,
        username="p123_pending_" + os.urandom(3).hex(),
    )
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/invites",
        json={"session_token": owner_token, "requires_approval": True},
    )
    check("approval invite created", status == 200, (status, body))
    invite_code = (body.get("invite") or {}).get("code") if status == 200 else None
    status, body = req(
        "POST",
        "/chat/api/join",
        json={"session_token": outsider_token, "code": invite_code},
    )
    check(
        "invite join creates a pending request",
        status == 200 and body.get("join_status") == "pending",
        (status, body),
    )
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}",
        params={"session_token": outsider_token},
    )
    check(
        "outsider does not see pending request count",
        status == 200 and body.get("view", {}).get("pending_requests") == 0,
        (status, body),
    )
    status, body = req(
        "GET",
        f"/chat/api/chats/{chat_id}",
        params={"session_token": owner_token},
    )
    check(
        "owner sees pending request count",
        status == 200 and body.get("view", {}).get("pending_requests", 0) >= 1,
        (status, body),
    )


def remaining_p3_rules() -> None:
    owner_login, owner_id, owner_device = register("p123-p3-owner")
    member_login, member_id, member_device = register("p123-p3-member")
    owner_token = login(owner_login, owner_device)
    chat_id = create_group(owner_token, "P123 p3", [member_id])

    status, body = create_poll(owner_token, chat_id, "duplicate?", ["same", "SAME"])
    check(
        "duplicate poll options rejected",
        status == 422 and (body.get("detail") or {}).get("code") == "duplicate_poll_option",
        (status, body),
    )

    status, body = req(
        "POST",
        "/chat/api/chats/1/leave",
        json={"session_token": owner_token},
    )
    check(
        "leaving the common chat is rejected",
        status == 409 and (body.get("detail") or {}).get("code") == "common_chat_protected",
        (status, body),
    )

    status, body = send_message(owner_token, chat_id, "pin me")
    assert status == 200, (status, body)
    message_id = int(body["message"]["message_id"])
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/pin",
        json={"session_token": owner_token, "message_id": message_id},
    )
    check("message pinned", status == 200, (status, body))
    status, body = req(
        "DELETE",
        f"/chat/api/chats/{chat_id}/messages/{message_id}",
        json={"session_token": owner_token},
    )
    check("pinned message deleted", status == 200, (status, body))
    check(
        "deleting a pinned message clears the pin",
        db_scalar("SELECT COUNT(*) FROM chats WHERE id = ? AND pinned_message_id IS NOT NULL", (chat_id,)) == 0,
    )


def main() -> None:
    if not DB_PATH:
        print("LC_TEST_DB is required", file=sys.stderr)
        sys.exit(2)
    private_room_cannot_be_published()
    automod_scans_polls()
    quota_counts_match()
    pending_requests_hidden_from_outsiders()
    remaining_p3_rules()
    print(f"RESULT: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

