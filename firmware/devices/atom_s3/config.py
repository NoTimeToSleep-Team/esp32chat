from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AtomS3Config:
    device_uid: str = "atom-s3-01"
    firmware_version: str = "0.8.3"
    server_base_url: str = "http://127.0.0.1:8000"
    ops_session_token: str | None = None

    def require_ops_session(self) -> str:
        token = (self.ops_session_token or "").strip()
        if not token:
            raise RuntimeError("ops_session_token is required for protected Atom actions")
        return token
