"""Integration regressions for the 2026-11-09 second pentest report.

Run against a disposable local server:
    LC_BASE=http://127.0.0.1:18081 LC_TEST_DB=<db path> python tests/server/test_security_fixes_2026_11_09b.py
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sqlite3
import sys
import time

import requests
import websockets

SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "server"))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18081")
WS_BASE = os.environ.get(
    "LC_WS_BASE",
    BASE.replace("https://", "wss://", 1).replace("http://", "ws://", 1),
)
DB_PATH = os.environ.get("LC_TEST_DB", "")

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


def set_mode(mode):
    assert DB_PATH, "LC_TEST_DB is required"
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute(
            "UPDATE mode_state SET access_mode = ? WHERE id = 1",
            (mode,),
        )
        connection.commit()
    finally:
        connection.close()


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


def create_group(token, title, member_ids):
    status, body = req(
        "POST",
        "/chat/api/chats",
        json={
            "session_token": token,
            "title": title,
            "member_ids": member_ids,
            "chat_type": "group",
            "username": "s2" + os.urandom(6).hex(),
        },
    )
    return status, body


def send(token, chat_id, text):
    return req(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        json={"session_token": token, "body_text": text},
    )


async def recv_type(ws, wanted, timeout=5):
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except Exception:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("type") == wanted:
            return data


async def recv_next(ws, timeout=5):
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    except Exception:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def ws_checks(chat_id, token):
    uri = f"{WS_BASE}/realtime/chat/{chat_id}?session_token={token}"
    async with websockets.connect(uri, max_size=200000) as ws:
        hello = await recv_type(ws, "realtime.connected")
        if hello is None:
            return "no realtime.connected", False

        await ws.send(
            json.dumps(
                {
                    "type": "chat.send",
                    "body_text": "x" * 5000,
                }
            )
        )
        oversized = await recv_type(ws, "error")
        oversized_ok = (
            oversized is not None
            and oversized.get("error", {}).get("code") == "message_too_long"
        )

        rate_limited = False
        for index in range(35):
            await ws.send(
                json.dumps(
                    {
                        "type": "chat.send",
                        "body_text": f"ws-rate-{index}",
                    }
                )
            )
            # Drain events until chat.ack or error.  The room echo arrives
            # before the ack and is intentionally ignored here.
            deadline = asyncio.get_event_loop().time() + 5
            while True:
                if asyncio.get_event_loop().time() > deadline:
                    break
                event = await recv_next(ws, timeout=2)
                if event is None:
                    break
                event_type = event.get("type")
                if event_type == "chat.ack":
                    break
                if event_type == "error":
                    if event.get("error", {}).get("code") == "rate_limited":
                        rate_limited = True
                    break
            if rate_limited:
                break
        return oversized_ok, rate_limited


def main():
    global failed

    # H1: closed-mode registration must go through the application flow.
    set_mode("closed")
    status, body = req(
        "POST",
        "/auth/register",
        json={
            "login": "closed-" + os.urandom(4).hex(),
            "password": "Sec-pass-12345",
            "phone": "No Phone",
            "device_id": "web-" + os.urandom(5).hex(),
            "client_kind": "web",
        },
    )
    check(
        "H1 closed registration rejected",
        status == 403 and detail_code(body) == "registration_closed",
        (status, body),
    )
    set_mode("open")

    # L1: password login must not mint device sessions.
    status, body = req(
        "POST",
        "/auth/login",
        json={
            "login": "admin",
            "password": "wrong",
            "client_kind": "device",
            "device_id": "dev-probe",
        },
    )
    check(
        "L1 device password login rejected",
        status == 403 and detail_code(body) == "device_session_required",
        (status, body),
    )

    # M3: trailing-slash redirect must not reflect the Host header.
    response = requests.get(
        BASE + "/chat/",
        headers={"Host": "evil.example"},
        timeout=10,
        allow_redirects=False,
    )
    location = response.headers.get("location", "")
    check(
        "M3 redirect is origin-relative",
        response.status_code in (307, 308)
        and "evil.example" not in location
        and location.startswith("/"),
        (response.status_code, location),
    )

    alice, alice_id, _ = register("s2-alice")
    bob, bob_id, _ = register("s2-bob")
    carol, carol_id, _ = register("s2-carol")

    # M2: a block cannot be bypassed by creating a group with the blocker.
    status, body = req(
        "POST",
        f"/chat/api/blocks/{alice_id}",
        json={"session_token": bob},
    )
    check("M2 blocker can block", status == 200, (status, body))
    status, body = create_group(alice, "blocked group", [bob_id])
    check(
        "M2 group creation blocked",
        status == 403 and detail_code(body) == "blocked",
        (status, body),
    )

    status, body = create_group(alice, "member add target", [carol_id])
    check("M2 control group created", status == 200, (status, body))
    chat_id = body["chat"]["chat_id"] if status == 200 else 0
    status, body = req(
        "POST",
        f"/chat/api/chats/{chat_id}/members",
        json={"session_token": alice, "user_id": bob_id},
    )
    check(
        "M2 add-member blocked",
        status == 403 and detail_code(body) == "blocked",
        (status, body),
    )

    # H2: WS send length and rate limit.
    status, body = create_group(alice, "ws security", [carol_id])
    check("H2 websocket chat created", status == 200, (status, body))
    ws_chat_id = body["chat"]["chat_id"] if status == 200 else 0
    oversized_ok, rate_limited = asyncio.run(ws_checks(ws_chat_id, alice))
    check("H2 websocket rejects >4000 chars", oversized_ok)
    check("H2 websocket rate limit triggers", rate_limited)

    # L2: a kicked author cannot edit or delete their old messages.
    status, body = send(carol, ws_chat_id, "message before kick")
    check("L2 message sent", status == 200, (status, body))
    message_id = body["message"]["message_id"] if status == 200 else 0
    status, body = req(
        "DELETE",
        f"/chat/api/chats/{ws_chat_id}/members/{carol_id}",
        json={"session_token": alice},
    )
    check("L2 kick succeeds", status == 200, (status, body))
    status, body = req(
        "PUT",
        f"/chat/api/chats/{ws_chat_id}/messages/{message_id}",
        json={"session_token": carol, "body_text": "edited after kick"},
    )
    check(
        "L2 edit after kick rejected",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )
    status, body = req(
        "DELETE",
        f"/chat/api/chats/{ws_chat_id}/messages/{message_id}",
        json={"session_token": carol},
    )
    check(
        "L2 delete after kick rejected",
        status == 403 and detail_code(body) == "forbidden",
        (status, body),
    )

    # M1 policy exception is intentional: guests may DM, but only with
    # anti-spam limits.  They still cannot create groups.
    guest_token, _guest_id = guest()
    status, body = req(
        "POST",
        "/chat/api/dm",
        json={"session_token": guest_token, "target_user_id": alice_id},
    )
    check("guest DM still allowed", status == 200, (status, body))
    guest_dm_id = body["chat"]["chat_id"] if status == 200 else 0
    status, body = send(guest_token, guest_dm_id, "guest hello")
    check("guest DM send still allowed", status == 200, (status, body))
    status, body = create_group(guest_token, "guest group", [alice_id])
    check(
        "guest group creation still rejected",
        status == 403 and detail_code(body) == "guest_forbidden",
        (status, body),
    )

    # Proxy SSRF helpers: loopback/link-local and non-web ports are denied.
    from app.services.http_proxy import ProxyDestinationDenied, _connect_public

    for host, port, label in [
        ("127.0.0.1", 80, "loopback"),
        ("169.254.169.254", 80, "link-local metadata"),
        ("1.1.1.1", 22, "non-web port"),
    ]:
        try:
            _connect_public(host, port)
            blocked = False
        except (ProxyDestinationDenied, OSError):
            blocked = True
        check(f"proxy blocks {label}", blocked)

    print(f"RESULT: {passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
