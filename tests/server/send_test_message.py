"""Send a test message to a chat on the server (hardware smoke test helper).

Usage:
    .venv\\Scripts\\python.exe tests\\server\\send_test_message.py "text" [chat_id]
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("LC_BASE", "http://169.254.93.1:18080")
ADMIN_LOGIN = os.environ.get("LC_ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("LC_ADMIN_PASSWORD", "7428")


def request(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else f"test message {int(time.time())}"
    chat_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    status, body = request(
        "POST",
        "/auth/login",
        {"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD, "client_kind": "web"},
    )
    token = str(body.get("session", {}).get("token", "")) if isinstance(body, dict) else ""
    if status != 200 or not token:
        print("login failed:", status, str(body)[:200])
        return 1

    if chat_id is None:
        status, body = request("GET", f"/chat/api/chats?session_token={token}")
        if status != 200:
            print("chats failed:", status, str(body)[:200])
            return 1
        items = body.get("items", [])
        if not items:
            print("no chats")
            return 1
        for item in items:
            if item.get("kind") == "common":
                chat_id = int(item["chat_id"])
                break
        if chat_id is None:
            chat_id = int(items[0]["chat_id"])
        print("chats:", [(i["chat_id"], i["kind"], i["title"]) for i in items])
        print("using chat_id:", chat_id)

    status, body = request(
        "POST",
        f"/chat/api/chats/{chat_id}/messages",
        {"session_token": token, "body_text": text},
    )
    print("send:", status, str(body)[:200])
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
