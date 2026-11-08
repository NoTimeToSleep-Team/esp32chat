"""Admin boundary regression: chat admin must not reach host/hardware surfaces.

Usage:
    LC_BASE=http://127.0.0.1:18080 LC_ADMIN_PASSWORD=... .venv\Scripts\python.exe tests\server\test_admin_infrastructure_boundary.py
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

BASE = os.environ.get("LC_BASE", "http://127.0.0.1:18080")
ADMIN_PASSWORD = os.environ.get("LC_ADMIN_PASSWORD", "")
passed = 0
failed = 0


def check(name, condition, extra=""):
    global passed, failed
    if condition:
        passed += 1
        print("PASS ", name)
    else:
        failed += 1
        print("FAIL ", name, extra)


def request(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


status, html = request("GET", "/admin")
check("admin shell loads", status == 200, status)
check("no System tab in admin shell", '["system"' not in html)
check("no Network tab in admin shell", '["network"' not in html)
check("no reboot UI", "reboot-btn" not in html and "/ops/api/reboot" not in html)
check("no system renderer", "renderSystem" not in html and "renderNetwork" not in html)

status, body = request("GET", "/openapi.json")
check("openapi available", status == 200, status)
paths = set(json.loads(body).get("paths", {})) if status == 200 else set()
forbidden = (
    "/ops",
    "/admin/network",
    "/admin/api/deployment",
    "/admin/api/modules",
    "/rfid",
    "/api/m5tab",
    "/devices/api/edge",
    "/system",
)
exposed = [p for p in paths if any(p == f or p.startswith(f + "/") for f in forbidden)]
check("no infrastructure paths in OpenAPI", not exposed, exposed[:10])

status, body = request(
    "POST",
    "/auth/login",
    {"login": "admin", "password": ADMIN_PASSWORD, "device_id": "test-admin-web", "client_kind": "web"},
)
check("admin can log in", status == 200, status)
token = ""
if status == 200:
    token = json.loads(body)["session"]["token"]

infra_requests = [
    ("GET", "/ops/api/state"),
    ("GET", "/ops/api/system-health"),
    ("POST", "/ops/api/reboot"),
    ("POST", "/ops/api/restart-service"),
    ("GET", "/ops/system-health"),
    ("GET", "/admin/network/interfaces"),
    ("POST", "/admin/network/services/restart"),
    ("GET", "/admin/api/deployment/status"),
    ("GET", "/admin/api/modules"),
    ("GET", "/rfid/api/cards"),
    ("GET", "/api/m5tab/info"),
    ("GET", "/devices/api/edge/capabilities"),
    ("GET", "/system"),
]
for method, path in infra_requests:
    status, _ = request(method, path + "?session_token=" + token)
    check(f"{method} {path.split('?')[0]} is hidden", status == 404, status)

status, body = request("GET", "/admin/users?session_token=" + token)
check("chat admin users API still works", status == 200, status)
status, body = request("GET", "/chat/api/chats?session_token=" + token)
check("chat API still works", status == 200, status)
status, body = request("GET", "/mode")
check("access-mode API still works", status == 200, status)
status, body = request("POST", "/auth/logout", {"session_token": token})
check("logout works", status == 200, status)
status, body = request("GET", "/health")
check("health works", status == 200, status)

print(f"RESULT: {passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
