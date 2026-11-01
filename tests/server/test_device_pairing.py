"""Integration test: device pairing by 6-digit code + challenge-response session.

Runs against a locally started server (default http://127.0.0.1:18080).
Usage:
    .venv\\Scripts\\python.exe tests\\server\\test_device_pairing.py
"""

from __future__ import annotations

import hashlib
import hmac
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
    device_id = f"cp-test-{int(time.time())}"
    secret = os.urandom(32)
    secret_hash = hashlib.sha256(secret).hexdigest()
    secret_key = bytes.fromhex(secret_hash)

    status, data = request(
        "POST",
        "/auth/login",
        {"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD, "client_kind": "web"},
    )
    token = str(data.get("session", {}).get("token", ""))
    check("admin login", status == 200 and len(token) >= 8, f"{status} {str(data)[:140]}")
    if not token:
        return 1

    status, data = request(
        "POST",
        "/devices/api/pair/request",
        {
            "device_id": device_id,
            "device_type": "cardputer",
            "name": "Cardputer Test",
            "device_secret_hash": secret_hash,
        },
    )
    pairing_id = str(data.get("pairing_id", ""))
    code = str(data.get("code", ""))
    check(
        "pair request returns code",
        status == 200 and len(code) == 6 and code.isdigit() and len(pairing_id) == 32,
        f"{status} {str(data)[:140]}",
    )

    status, data = request("GET", f"/devices/api/pair/status?pairing_id={pairing_id}")
    check("status is pending", status == 200 and data.get("pairing_status") == "pending", f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/devices/api/pair/claim",
        {"session_token": token, "code": code},
    )
    claimed_device = data.get("device", {}) if isinstance(data, dict) else {}
    check(
        "claim by code",
        status == 200 and claimed_device.get("device_id") == device_id,
        f"{status} {str(data)[:140]}",
    )

    status, data = request("GET", f"/devices/api/pair/status?pairing_id={pairing_id}")
    check("status is paired", status == 200 and data.get("paired") is True, f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/devices/api/pair/claim",
        {"session_token": token, "code": code},
    )
    check("second claim rejected", status in (409, 410), f"{status} {str(data)[:140]}")

    status, data = request("POST", "/auth/device-session", {"device_id": device_id})
    check("session without proof rejected", status == 401, f"{status} {str(data)[:140]}")

    status, data = request("POST", "/auth/device-challenge", {"device_id": device_id})
    challenge = str(data.get("challenge", ""))
    check("challenge issued", status == 200 and len(challenge) == 32, f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/auth/device-session",
        {"device_id": device_id, "challenge": challenge, "proof": "00" * 32},
    )
    check("bad proof rejected", status == 401, f"{status} {str(data)[:140]}")

    status, data = request("POST", "/auth/device-challenge", {"device_id": device_id})
    challenge = str(data.get("challenge", ""))
    proof = hmac.new(secret_key, challenge.encode("ascii"), hashlib.sha256).hexdigest()
    status, data = request(
        "POST",
        "/auth/device-session",
        {"device_id": device_id, "challenge": challenge, "proof": proof},
    )
    device_token = str(data.get("session", {}).get("token", ""))
    check("device session with proof", status == 200 and len(device_token) >= 8, f"{status} {str(data)[:140]}")

    status, data = request("GET", f"/chat/api/chats?session_token={device_token}")
    check("device token cannot use web API", status == 403, f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/devices/api/pair/reset",
        {"session_token": device_token, "device_id": device_id},
    )
    check("device token cannot use pair reset", status == 403, f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/devices/api/unpair",
        {"session_token": token, "device_id": device_id},
    )
    check("unpair", status == 200, f"{status} {str(data)[:140]}")

    status, data = request("POST", "/auth/device-challenge", {"device_id": device_id})
    check("challenge after unpair rejected", status == 404, f"{status} {str(data)[:140]}")

    new_secret_hash = hashlib.sha256(b"another-device-secret").hexdigest()
    status, data = request(
        "POST",
        "/devices/api/pair/request",
        {
            "device_id": device_id,
            "device_type": "cardputer",
            "name": "Cardputer Test",
            "device_secret_hash": new_secret_hash,
        },
    )
    check("different secret cannot replace known identity", status == 409, f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/devices/api/pair/reset",
        {"session_token": token, "device_id": device_id},
    )
    check("admin can reset device identity", status == 200, f"{status} {str(data)[:140]}")

    status, data = request(
        "POST",
        "/devices/api/pair/request",
        {
            "device_id": device_id,
            "device_type": "cardputer",
            "name": "Cardputer Test",
            "device_secret_hash": new_secret_hash,
        },
    )
    check("new secret accepted after reset", status == 200, f"{status} {str(data)[:140]}")

    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
