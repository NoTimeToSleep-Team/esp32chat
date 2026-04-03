from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TEmbedCC1101Config:
    profile_id: str = "t_embed_cc1101"
    base_url: str = "http://127.0.0.1:8000"
    request_timeout_s: float = 5.0
    client_kind: str = "device"
