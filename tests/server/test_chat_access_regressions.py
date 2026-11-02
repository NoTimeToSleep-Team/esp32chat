"""Integration regressions: chat joins, group-admin limits, WebSocket kick.

Covers F8, F9, F10, F11 and F12 from the 2026-11-02 assessment.
Usage:
    LC_BASE=http://127.0.0.1:18080 .venv\\Scripts\\python.exe tests\\server\\test_chat_access_regressions.py
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time

import requests
import websockets
from websockets.exceptions import ConnectionClosed

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18080")
WS_BASE = os.environ.get(
    "LC_WS_BASE",
    BASE.replace("https://", "wss://", 1).replace("http://", "ws://", 1),
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


def register(prefix):
    login = prefix + "-" + os.urandom(4).hex()
    status, body = req(
        "POST",
        "/auth/register",
        json={
            "login": login,
            "password": "Sec-pass-12345",
            "phone": "+7999" + str(random.randint(1000000, 9999999)),
            "device_id": "web-" + os.urandom(5).hex(),
            "client_kind": "web",
        },
    )
    assert status == 200, (status, body)
    return body["session"]["token"], body["user"]["id"], login


def guest():
    status, body = req("POST", "/auth/guest", json={"client_kind": "web"})
    assert status == 200, (status, body)
    return body["session"]["token"], body["user"]["id"]


def create_group(token, title, member_ids, *, is_public=False, history_visible=True):
    status, body = req(
        "POST",
        "/chat/api/chats",
        json={
            "session_token": token,
            "title": title,
            "member_ids": member_ids,
            "chat_type": "group",
            "is_public": is_public,
            "history_visible": history_visible,
            "username": "r5" + os.urandom(5).hex(),
        },
    )
    assert status == 200, (status, body)
    return body["chat"]["chat_id"]


def create_private(token, title):
    status, body = req(
        "POST",
        "/chat/api/private",
        json={"session_token": token, "title": title},
    )
    assert status == 200, (status, body)
    return body["chat"]["chat_id"]


def send(token, chat_id, text):
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        json={"session_token": token, "body_text": text},
    )
    assert status == 200, (status, body)
    return body["message"]["message_id"]


def invite(token, chat_id):
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/invites",
        json={"session_token": token},
    )
    assert status == 200, (status, body)
    return body["invite"]["code"]


owner, owner_id, _ = register("r5-owner")
member, member_id, _ = register("r5-member")
bob, bob_id, _ = register("r5-bob")
carol, carol_id, _ = register("r5-carol")
guest_token, guest_id = guest()

# --- F8: closed group cannot be joined by numeric id -----------------------
f8_chat = create_group(owner, "r5-f8 closed " + os.urandom(3).hex(), [member_id])
send(owner, f8_chat, "R5_DEFAULT_SECRET")
status, body = req(
    "POST",
    "/chat/api/join",
    json={"session_token": bob, "chat_id": f8_chat},
)
check("F8 normal join stays blocked", status == 403 and detail_code(body) == "chat_private", (status, body))
status, body = req(
    "POST",
    f"/chat/api/private/{f8_chat}/join",
    json={"session_token": bob, "room_code": None},
)
check(
    "F8 private endpoint rejects closed group",
    status == 403 and detail_code(body) == "invite_required",
    (status, body),
)
status, body = req(
    "GET",
    f"/chat/api/chats/{f8_chat}/messages",
    params={"session_token": bob},
)
check("F8 outsider cannot read", status in (403, 404), (status, body))

# Kick/rejoin: add explicitly, then remove; no numeric rejoin.
status, body = req(
    "POST",
    f"/chat/api/chats/{f8_chat}/members",
    json={"session_token": owner, "user_id": bob_id},
)
check("F8 owner can add member", status == 200, (status, body))
status, body = req(
    "DELETE",
    f"/chat/api/chats/{f8_chat}/members/{bob_id}",
    json={"session_token": owner},
)
check("F8 owner can kick", status == 200, (status, body))
status, body = req(
    "POST",
    f"/chat/api/private/{f8_chat}/join",
    json={"session_token": bob, "room_code": None},
)
check(
    "F8 kicked user cannot rejoin by id",
    status == 403 and detail_code(body) == "invite_required",
    (status, body),
)

# Block must also block an otherwise valid invite.
code = invite(owner, f8_chat)
status, body = req(
    "POST",
    f"/chat/api/blocks/{bob_id}",
    json={"session_token": owner},
)
check("F8 owner can block", status == 200, (status, body))
status, body = req(
    "POST",
    f"/chat/api/chats/{f8_chat}/members",
    json={"session_token": owner, "user_id": bob_id},
)
check(
    "F8 blocked user cannot be added directly",
    status == 403 and detail_code(body) == "blocked",
    (status, body),
)
status, body = req(
    "POST",
    "/chat/api/join",
    json={"session_token": bob, "code": code},
)
check(
    "F8 blocked user rejected on invite",
    status == 403 and detail_code(body) == "blocked",
    (status, body),
)
status, body = req(
    "DELETE",
    f"/chat/api/blocks/{bob_id}",
    json={"session_token": owner},
)
check("F8 unblock", status == 200, (status, body))

# Public joins must remain unaffected.
public_chat = create_group(
    owner,
    "r5 public " + os.urandom(3).hex(),
    [member_id],
    is_public=True,
)
send(owner, public_chat, "R5_PUBLIC_MESSAGE")
status, body = req(
    "POST",
    "/chat/api/join",
    json={"session_token": bob, "chat_id": public_chat},
)
check("public chat still joinable", status == 200, (status, body))
status, body = req(
    "GET",
    f"/chat/api/chats/{public_chat}/messages",
    params={"session_token": bob},
)
check("public chat readable after join", status == 200, (status, body))
status, body = req(
    "DELETE",
    f"/chat/api/chats/{public_chat}",
    json={"session_token": owner},
)
check("public chat cleanup", status == 200, (status, body))

# --- F12: guest cannot use invite or direct add ---------------------------
group_code = invite(owner, f8_chat)
erin, erin_id, _ = register("r5-erin")
status, body = req(
    "POST",
    "/chat/api/join",
    json={"session_token": erin, "code": group_code},
)
check("F8 regular user with invite joins closed group", status == 200, (status, body))
status, body = req(
    "GET",
    f"/chat/api/chats/{f8_chat}/messages",
    params={"session_token": erin},
)
check("F8 invited user can read", status == 200, (status, body))
status, body = req(
    "DELETE",
    f"/chat/api/chats/{f8_chat}/members/{erin_id}",
    json={"session_token": owner},
)
check("F8 invited user can be kicked", status == 200, (status, body))
status, body = req(
    "POST",
    f"/chat/api/private/{f8_chat}/join",
    json={"session_token": erin, "room_code": None},
)
check(
    "F8 invited user cannot rejoin by id",
    status == 403 and detail_code(body) == "invite_required",
    (status, body),
)

status, body = req(
    "POST",
    "/chat/api/join",
    json={"session_token": guest_token, "code": group_code},
)
check(
    "F12 guest rejected on group invite",
    status == 403 and detail_code(body) == "guest_forbidden",
    (status, body),
)
status, body = req(
    "POST",
    f"/chat/api/chats/{f8_chat}/members",
    json={"session_token": owner, "user_id": guest_id},
)
check(
    "F12 guest rejected on direct add",
    status == 403 and detail_code(body) == "guest_forbidden",
    (status, body),
)

true_private = create_private(owner, "r5 true private " + os.urandom(3).hex())
private_code = invite(owner, true_private)
status, body = req(
    "POST",
    "/chat/api/join",
    json={"session_token": guest_token, "code": private_code},
)
check(
    "F12 guest rejected on true-private invite",
    status == 403 and detail_code(body) == "guest_forbidden",
    (status, body),
)
status, body = req(
    "POST",
    f"/chat/api/private/{true_private}/join",
    json={"session_token": guest_token, "room_code": None},
)
check(
    "F12 guest rejected on private endpoint",
    status == 403 and detail_code(body) == "guest_forbidden",
    (status, body),
)

# --- F10: group admin cannot publish, seize or delete ---------------------
f10_chat = create_group(owner, "r5-f10 owned " + os.urandom(3).hex(), [member_id])
send(owner, f10_chat, "R5_F10_PRIVATE_SECRET")
status, body = req(
    "POST",
    f"/chat/api/chats/{f10_chat}/members/{member_id}/role",
    json={"session_token": owner, "role": "admin"},
)
check("F10 owner grants group admin", status == 200, (status, body))
status, body = req(
    "PATCH",
    f"/chat/api/chats/{f10_chat}",
    json={"session_token": member, "title": "r5 group admin title"},
)
check("F10 group admin may edit ordinary info", status == 200, (status, body))
status, body = req(
    "PATCH",
    f"/chat/api/chats/{f10_chat}",
    json={"session_token": member, "is_public": True, "history_visible": True},
)
check(
    "F10 group admin cannot publish",
    status == 403 and detail_code(body) == "owner_only",
    (status, body),
)
status, body = req(
    "PATCH",
    f"/chat/api/chats/{f10_chat}",
    json={"session_token": member, "history_visible": False},
)
check(
    "F10 group admin cannot change history visibility",
    status == 403 and detail_code(body) == "owner_only",
    (status, body),
)
status, body = req(
    "PATCH",
    f"/chat/api/chats/{f10_chat}",
    json={"session_token": member, "username": "r5groupadmin" + os.urandom(3).hex()},
)
check(
    "F10 group admin cannot set public link name",
    status == 403 and detail_code(body) == "owner_only",
    (status, body),
)
status, body = req(
    "GET",
    f"/chat/api/chats/{f10_chat}/messages",
    params={"session_token": carol},
)
check("F10 chat remains private", status in (403, 404), (status, body))
status, body = req(
    "POST",
    f"/chat/api/chats/{f10_chat}/owner",
    json={"session_token": member, "target_user_id": member_id},
)
check(
    "F10 group admin cannot seize ownership",
    status == 403 and detail_code(body) == "owner_only",
    (status, body),
)
status, body = req(
    "DELETE",
    f"/chat/api/chats/{f10_chat}",
    json={"session_token": member},
)
check(
    "F10 group admin cannot delete",
    status == 403 and detail_code(body) == "owner_only",
    (status, body),
)
status, body = req(
    "POST",
    f"/chat/api/chats/{f10_chat}/owner",
    json={"session_token": owner, "target_user_id": member_id},
)
check("F10 owner can transfer ownership", status == 200, (status, body))
status, body = req(
    "DELETE",
    f"/chat/api/chats/{f10_chat}",
    json={"session_token": member},
)
check("F10 new owner can delete", status == 200, (status, body))

# --- F9: non-member read/draft contract -----------------------------------
status, body = req(
    "POST",
    f"/chat/api/chats/{f8_chat}/read",
    json={"session_token": carol, "message_id": 1},
)
check(
    "F9 non-member read returns 403",
    status == 403 and detail_code(body) == "join_required",
    (status, body),
)
status, body = req(
    "POST",
    f"/chat/api/chats/{f8_chat}/draft",
    json={"session_token": carol, "text": "r5 draft"},
)
check(
    "F9 non-member draft returns 403",
    status == 403 and detail_code(body) == "join_required",
    (status, body),
)

# --- F11: kicked member WebSocket is closed --------------------------------
async def recv_type(ws, wanted, timeout=5):
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except ConnectionClosed:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("type") == wanted:
            return data


async def wait_closed(ws, timeout=5):
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            await asyncio.wait_for(ws.recv(), timeout=remaining)
        except ConnectionClosed as exc:
            return exc.code


async def check_ws_kick(chat_id):
    member_uri = f"{WS_BASE}/realtime/chat/{chat_id}?session_token={member}"
    async with websockets.connect(member_uri, max_size=200000) as ws:
        hello = await recv_type(ws, "realtime.connected")
        if hello is None:
            return "no realtime.connected"
        response = await asyncio.to_thread(
            requests.delete,
            BASE + f"/chat/api/chats/{chat_id}/members/{member_id}",
            json={"session_token": owner},
            timeout=20,
        )
        if response.status_code != 200:
            return f"kick={response.status_code} {response.text[:200]}"
        close_code = await wait_closed(ws)
        return close_code


ws_chat = create_group(owner, "r5-ws kick " + os.urandom(3).hex(), [member_id])
close_code = asyncio.run(check_ws_kick(ws_chat))
check("F11 kicked WebSocket closed with 4403", close_code == 4403, repr(close_code))
status, body = req(
    "GET",
    f"/chat/api/chats/{ws_chat}/messages",
    params={"session_token": member},
)
check("F11 kicked member loses HTTP access", status in (403, 404), (status, body))

# Cleanup.
for chat_id, token in [(f8_chat, owner), (true_private, owner), (ws_chat, owner)]:
    status, body = req(
        "DELETE",
        f"/chat/api/chats/{chat_id}",
        json={"session_token": token},
    )
    check(f"cleanup chat {chat_id}", status in (200, 403, 404), (status, body))

print(f"RESULT: {passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
