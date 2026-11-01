from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import DevicePairRequest, PairedDevice

PAIRING_CODE_TTL_MS = 5 * 60 * 1000
CHALLENGE_TTL_MS = 2 * 60 * 1000
_CODE_ATTEMPTS = 10


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class DevicePairingError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


# Challenge store: device_id -> (challenge, expires_at_ms). In-memory on purpose:
# a server restart simply forces the device to request a new challenge.
_challenges: dict[str, tuple[str, int]] = {}
_challenges_lock = threading.Lock()


def _issue_challenge(device_id: str) -> tuple[str, int]:
    challenge = secrets.token_hex(16)
    expires_at = _now_ms() + CHALLENGE_TTL_MS
    with _challenges_lock:
        _challenges[device_id] = (challenge, expires_at)
    return challenge, CHALLENGE_TTL_MS


def _consume_challenge(device_id: str, challenge: str) -> bool:
    now = _now_ms()
    with _challenges_lock:
        entry = _challenges.pop(device_id, None)
    if entry is None:
        return False
    expected, expires_at = entry
    if expires_at <= now:
        return False
    return hmac.compare_digest(expected, challenge.strip().lower())


class DevicePairingService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def create_request(
        self,
        *,
        device_id: str,
        device_type: str,
        name: str,
        device_secret_hash: str,
    ) -> DevicePairRequest:
        device_id = device_id.strip()
        device_type = device_type.strip()
        name = name.strip()[:64]
        secret_hash = device_secret_hash.strip().lower()

        if not device_id or len(device_id) > 128:
            raise DevicePairingError("invalid_device_id", "device_id must be 1..128 characters", 422)
        if len(secret_hash) != 64 or any(ch not in "0123456789abcdef" for ch in secret_hash):
            raise DevicePairingError("invalid_secret_hash", "device_secret_hash must be a hex sha256", 422)

        now_ms = _now_ms()
        expires_at_ms = now_ms + PAIRING_CODE_TTL_MS
        pairing_id = secrets.token_hex(16)

        with self._connect() as connection:
            # A known device identity may only be re-paired with the same
            # secret commitment.  Otherwise an anonymous first-come request
            # could replace a real device's secret and hijack its id.  An
            # administrator can explicitly reset the identity if a device is
            # lost or its secret must be rotated.
            known = connection.execute(
                "SELECT status, device_secret_hash FROM device_pairings WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if known is not None:
                stored_hash = str(known["device_secret_hash"] or "").strip().lower()
                if not stored_hash or not hmac.compare_digest(stored_hash, secret_hash):
                    raise DevicePairingError(
                        "device_identity_mismatch",
                        "Device identity is already bound; an administrator must reset it before re-pairing",
                        409,
                    )

            existing = connection.execute(
                """
                SELECT pairing_id, device_id, device_type, name, code,
                       device_secret_hash, created_at_ms, expires_at_ms
                FROM device_pair_requests
                WHERE device_id = ?
                  AND status = 'pending'
                  AND expires_at_ms > ?
                ORDER BY created_at_ms DESC
                LIMIT 1
                """,
                (device_id, now_ms),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(str(existing["device_secret_hash"]), secret_hash):
                    raise DevicePairingError(
                        "pairing_pending",
                        "Pairing is already in progress for this device",
                        409,
                    )
                return DevicePairRequest(
                    pairing_id=str(existing["pairing_id"]),
                    device_id=str(existing["device_id"]),
                    device_type=str(existing["device_type"]),
                    name=str(existing["name"]),
                    code=str(existing["code"]),
                    created_at_ms=int(existing["created_at_ms"]),
                    expires_at_ms=int(existing["expires_at_ms"]),
                    status="pending",
                )

            connection.execute(
                """
                UPDATE device_pair_requests
                SET status = 'expired'
                WHERE device_id = ? AND status = 'pending' AND expires_at_ms <= ?
                """,
                (device_id, now_ms),
            )
            code = ""
            for _ in range(_CODE_ATTEMPTS):
                candidate = f"{secrets.randbelow(1_000_000):06d}"
                try:
                    connection.execute(
                        """
                        INSERT INTO device_pair_requests(
                            pairing_id, device_id, device_type, name, code,
                            device_secret_hash, created_at_ms, expires_at_ms, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                        """,
                        (pairing_id, device_id, device_type, name, candidate, secret_hash, now_ms, expires_at_ms),
                    )
                    code = candidate
                    break
                except sqlite3.IntegrityError:
                    continue
            if not code:
                raise DevicePairingError("pairing_unavailable", "Could not allocate a pairing code, retry later", 503)

        return DevicePairRequest(
            pairing_id=pairing_id,
            device_id=device_id,
            device_type=device_type,
            name=name,
            code=code,
            created_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            status="pending",
        )

    def reset_identity(self, device_id: str) -> bool:
        normalized = device_id.strip()
        if not normalized:
            raise DevicePairingError("invalid_device_id", "device_id is required", 422)
        now_ms = _now_ms()
        with self._connect() as connection:
            changed = connection.execute(
                "DELETE FROM device_pairings WHERE device_id = ?",
                (normalized,),
            ).rowcount
            connection.execute(
                """
                UPDATE device_pair_requests
                SET status = 'expired'
                WHERE device_id = ? AND status = 'pending' AND expires_at_ms > ?
                """,
                (normalized, now_ms),
            )
        return changed > 0

    def get_status(self, pairing_id: str) -> str:
        pairing_id = pairing_id.strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, expires_at_ms FROM device_pair_requests WHERE pairing_id = ?",
                (pairing_id,),
            ).fetchone()
            if row is None:
                raise DevicePairingError("pairing_not_found", "Pairing request not found", 404)
            status = str(row["status"])
            if status == "pending" and int(row["expires_at_ms"]) <= _now_ms():
                connection.execute(
                    "UPDATE device_pair_requests SET status = 'expired' WHERE pairing_id = ?",
                    (pairing_id,),
                )
                status = "expired"
        return status

    def claim(self, *, user_id: int, code: str) -> PairedDevice:
        code = code.strip()
        if len(code) != 6 or not code.isdigit():
            raise DevicePairingError("invalid_code", "Pairing code must be 6 digits", 422)

        now_ms = _now_ms()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT pairing_id, device_id, device_type, name, device_secret_hash, expires_at_ms, status
                FROM device_pair_requests
                WHERE code = ?
                ORDER BY created_at_ms DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            if row is None:
                raise DevicePairingError("code_not_found", "Pairing code not found", 404)
            if str(row["status"]) != "pending":
                raise DevicePairingError("code_expired", "Pairing code is no longer active", 410)
            if int(row["expires_at_ms"]) <= now_ms:
                connection.execute(
                    "UPDATE device_pair_requests SET status = 'expired' WHERE pairing_id = ?",
                    (row["pairing_id"],),
                )
                raise DevicePairingError("code_expired", "Pairing code has expired", 410)

            existing = connection.execute(
                "SELECT user_id, status, device_secret_hash FROM device_pairings WHERE device_id = ?",
                (row["device_id"],),
            ).fetchone()
            if existing is not None:
                stored_hash = str(existing["device_secret_hash"] or "").strip().lower()
                request_hash = str(row["device_secret_hash"] or "").strip().lower()
                if not stored_hash or not hmac.compare_digest(stored_hash, request_hash):
                    raise DevicePairingError(
                        "device_identity_mismatch",
                        "Device identity changed after this code was issued; request a new pairing code",
                        409,
                    )
            if (
                existing is not None
                and str(existing["status"]) == "active"
                and int(existing["user_id"]) != user_id
            ):
                raise DevicePairingError("already_paired", "Device is already paired to another account", 409)

            connection.execute(
                """
                INSERT INTO device_pairings(
                    device_id, user_id, device_type, paired_at_ms, status,
                    device_secret_hash, last_seen_ms, name
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    device_type = excluded.device_type,
                    paired_at_ms = excluded.paired_at_ms,
                    status = 'active',
                    device_secret_hash = excluded.device_secret_hash,
                    last_seen_ms = excluded.last_seen_ms,
                    name = excluded.name
                """,
                (
                    row["device_id"],
                    user_id,
                    str(row["device_type"]),
                    now_ms,
                    str(row["device_secret_hash"]),
                    now_ms,
                    str(row["name"]),
                ),
            )
            connection.execute(
                "UPDATE device_pair_requests SET status = 'claimed' WHERE pairing_id = ?",
                (row["pairing_id"],),
            )

        return PairedDevice(
            device_id=str(row["device_id"]),
            device_type=str(row["device_type"]),
            name=str(row["name"]),
            paired_at_ms=now_ms,
        )

    def issue_challenge(self, device_id: str) -> tuple[str, int]:
        device_id = device_id.strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, device_secret_hash FROM device_pairings WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        if (
            row is None
            or str(row["status"]) != "active"
            or len(str(row["device_secret_hash"] or "").strip()) != 64
        ):
            raise DevicePairingError("device_not_paired", "Device is not paired", 404)
        return _issue_challenge(device_id)

    def verify_session_proof(self, *, device_id: str, challenge: str, proof: str) -> int:
        device_id = device_id.strip()
        if not _consume_challenge(device_id, challenge):
            raise DevicePairingError("challenge_invalid", "Challenge is invalid or expired", 401)

        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, status, device_secret_hash FROM device_pairings WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if row is None or str(row["status"]) != "active":
                raise DevicePairingError("device_not_paired", "Device is not paired", 404)

            secret_hash = str(row["device_secret_hash"] or "").strip().lower()
            if len(secret_hash) != 64:
                raise DevicePairingError("device_proof_required", "Device has no secret, re-pair the device", 401)

            expected = hmac.new(
                bytes.fromhex(secret_hash),
                challenge.strip().lower().encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, proof.strip().lower()):
                raise DevicePairingError("invalid_proof", "Device proof is invalid", 401)

            connection.execute(
                "UPDATE device_pairings SET last_seen_ms = ? WHERE device_id = ?",
                (_now_ms(), device_id),
            )
            user_id = int(row["user_id"])

        return user_id
