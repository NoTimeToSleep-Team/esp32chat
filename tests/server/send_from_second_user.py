"""Create/use a second user and send a message to the common chat.

Used to verify hardware notifications (own messages are excluded from updates).

Usage:
    .venv\\Scripts\\python.exe tests\\server\\send_from_second_user.py ["text"]
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("LC_BASE", "http://169.254.93.1:18080")
LOGIN = os.environ.get("LC_USER2_LOGIN", "uitest2")
PASSWORD = os.environ.get("LC_USER2_PASSWORD", "uitest2pass123")
PHONE = os.environ.get("LC_USER2_PHONE", "+79990000002")


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
    text = sys.argv[1] if len(sys.argv) > 1 else f"notification test {int(time.time())}"

    status, body = request(
        "POST",
        "/auth/login",
        {"login": LOGIN, "password": PASSWORD, "client_kind": "web"},
    )
    if status != 200:
        status, body = request(
            "POST",
            "/auth/register",
            {
                "login": LOGIN,
                "password": PASSWORD,
                "phone": PHONE,
                "device_id": f"uitest2-{int(time.time())}",
                "client_kind": "web",
            },
        )
    token = str(body.get("session", {}).get("token", "")) if isinstance(body, dict) else ""
    if not token:
        print("login/register failed:", status, str(body)[:200])
        return 1
    print("user2:", body.get("user", {}).get("login"), "status:", status)

    status, body = request("GET", f"/chat/api/chats?session_token={token}")
    common_id = None
    for item in body.get("items", []):
        if item.get("kind") == "common":
            common_id = int(item["chat_id"])
            break
    if common_id is None:
        print("common chat not found:", str(body)[:200])
        return 1

    status, body = request(
        "POST",
        f"/chat/api/chats/{common_id}/messages",
        {"session_token": token, "body_text": text},
    )
    print("send:", status, str(body)[:140])
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
