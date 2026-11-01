"""Integration test: /chat/api/updates (new messages across all user chats).

Usage:
    .venv\\Scripts\\python.exe tests\\server\\test_chat_updates.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18080")
ADMIN_LOGIN = os.environ.get("LC_ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("LC_ADMIN_PASSWORD", "")

passed = 0
failed = 0


def check(name: str, condition: bool, extra: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {extra}")


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
    status, data = request(
        "POST",
        "/auth/login",
        {"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD, "client_kind": "web"},
    )
    token = str(data.get("session", {}).get("token", ""))
    check("admin login", status == 200 and len(token) >= 8, f"{status} {str(data)[:140]}")
    if not token:
        return 1

    status, data = request("GET", f"/chat/api/updates?session_token={token}&since_ms=0&limit=10")
    check(
        "updates endpoint responds",
        status == 200 and isinstance(data.get("items"), list) and "server_time_ms" in data,
        f"{status} {str(data)[:140]}",
    )

    before_ms = int(time.time() * 1000)
    status, data = request("GET", f"/chat/api/chats?session_token={token}")
    chats = data.get("items", [])
    common_id = None
    for item in chats:
        if item.get("kind") == "common":
            common_id = int(item["chat_id"])
            break
    check("common chat found", common_id is not None, str(chats)[:140])

    status, data = request(
        "POST",
        f"/chat/api/chats/{common_id}/messages",
        {"session_token": token, "body_text": f"updates-test-{int(time.time())}"},
    )
    check("message sent", status == 200, f"{status} {str(data)[:140]}")

    status, data = request(
        "GET",
        f"/chat/api/updates?session_token={token}&since_ms={before_ms}&limit=10",
    )
    own_ids = [item.get("author_login") for item in data.get("items", [])]
    check(
        "own messages excluded from updates",
        status == 200 and "admin" not in own_ids,
        f"{status} authors={own_ids}",
    )

    status, data = request(
        "GET",
        f"/chat/api/updates?session_token={token}&since_ms={int(time.time() * 1000) + 60000}",
    )
    check("future since_ms gives empty list", status == 200 and data.get("count") == 0, f"{status} {str(data)[:140]}")

    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
