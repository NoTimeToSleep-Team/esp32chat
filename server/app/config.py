from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class ConfigError(ValueError):
    """Raised when environment configuration is invalid."""


_PROFILES = {"dev", "test", "prod"}
_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}


@dataclass(frozen=True)
class Settings:
    profile: str
    host: str
    port: int
    reload: bool
    log_level: str
    database_url: str
    storage_root: str
    allowed_origins: tuple[str, ...]
    session_secret: str
    request_timeout_ms: int
    rate_limit_window_ms: int
    rate_limit_max_requests: int
    auth_rate_limit_window_ms: int
    auth_rate_limit_max_requests: int
    bruteforce_window_ms: int
    bruteforce_login_attempt_limit: int
    bruteforce_ip_attempt_limit: int
    bruteforce_block_ms: int


def _read_str(
    env: Mapping[str, str],
    name: str,
    default: str | None = None,
    *,
    allow_empty: bool = False,
) -> str:
    value = env.get(name, default)
    if value is None:
        raise ConfigError(f"Missing required setting: {name}")
    value = value.strip()
    if not allow_empty and not value:
        raise ConfigError(f"Setting {name} must not be empty")
    return value


def _read_int(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    min_value: int,
    max_value: int,
) -> int:
    raw = env.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"Setting {name} must be an integer") from exc
    if value < min_value or value > max_value:
        raise ConfigError(
            f"Setting {name} must be between {min_value} and {max_value}"
        )
    return value


def _read_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Setting {name} must be boolean-like")


def _read_origins(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw = _read_str(env, name, "*")
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not parts:
        raise ConfigError(f"Setting {name} must contain at least one origin")
    return parts


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env

    profile = _read_str(source, "LCS_PROFILE", "dev").lower()
    if profile not in _PROFILES:
        raise ConfigError("LCS_PROFILE must be one of: dev, test, prod")

    host = _read_str(source, "LCS_HOST", "127.0.0.1")
    port = _read_int(source, "LCS_PORT", 8000, min_value=1, max_value=65535)
    reload_enabled = _read_bool(source, "LCS_RELOAD", profile == "dev")

    log_level = _read_str(source, "LCS_LOG_LEVEL", "debug" if profile == "dev" else "info").lower()
    if log_level not in _LOG_LEVELS:
        raise ConfigError(
            "LCS_LOG_LEVEL must be one of: debug, info, warning, error, critical"
        )

    database_url = _read_str(
        source,
        "LCS_DATABASE_URL",
        "sqlite:///data/sqlite/local_chat.db",
    )
    if "://" not in database_url:
        raise ConfigError("LCS_DATABASE_URL must be a valid database URL")

    storage_root = _read_str(source, "LCS_STORAGE_ROOT", "data")

    allowed_origins = _read_origins(source, "LCS_ALLOWED_ORIGINS")
    session_secret = _read_str(source, "LCS_SESSION_SECRET", "dev-insecure-change-me")
    request_timeout_ms = _read_int(
        source,
        "LCS_REQUEST_TIMEOUT_MS",
        15000,
        min_value=1000,
        max_value=120000,
    )
    rate_limit_window_ms = _read_int(
        source,
        "LCS_RATE_LIMIT_WINDOW_MS",
        60000,
        min_value=1000,
        max_value=3600000,
    )
    rate_limit_max_requests = _read_int(
        source,
        "LCS_RATE_LIMIT_MAX_REQUESTS",
        240,
        min_value=10,
        max_value=100000,
    )
    auth_rate_limit_window_ms = _read_int(
        source,
        "LCS_AUTH_RATE_LIMIT_WINDOW_MS",
        60000,
        min_value=1000,
        max_value=3600000,
    )
    auth_rate_limit_max_requests = _read_int(
        source,
        "LCS_AUTH_RATE_LIMIT_MAX_REQUESTS",
        30,
        min_value=3,
        max_value=10000,
    )
    bruteforce_window_ms = _read_int(
        source,
        "LCS_BRUTEFORCE_WINDOW_MS",
        900000,
        min_value=10000,
        max_value=86400000,
    )
    bruteforce_login_attempt_limit = _read_int(
        source,
        "LCS_BRUTEFORCE_LOGIN_ATTEMPT_LIMIT",
        5,
        min_value=2,
        max_value=1000,
    )
    bruteforce_ip_attempt_limit = _read_int(
        source,
        "LCS_BRUTEFORCE_IP_ATTEMPT_LIMIT",
        25,
        min_value=5,
        max_value=10000,
    )
    bruteforce_block_ms = _read_int(
        source,
        "LCS_BRUTEFORCE_BLOCK_MS",
        900000,
        min_value=10000,
        max_value=86400000,
    )

    if profile == "prod":
        if reload_enabled:
            raise ConfigError("LCS_RELOAD must be false for prod profile")
        if len(session_secret) < 16 or session_secret == "dev-insecure-change-me":
            raise ConfigError("LCS_SESSION_SECRET must be set and >=16 chars for prod")
        if "*" in allowed_origins:
            raise ConfigError("LCS_ALLOWED_ORIGINS must be explicit in prod")

    return Settings(
        profile=profile,
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=log_level,
        database_url=database_url,
        storage_root=storage_root,
        allowed_origins=allowed_origins,
        session_secret=session_secret,
        request_timeout_ms=request_timeout_ms,
        rate_limit_window_ms=rate_limit_window_ms,
        rate_limit_max_requests=rate_limit_max_requests,
        auth_rate_limit_window_ms=auth_rate_limit_window_ms,
        auth_rate_limit_max_requests=auth_rate_limit_max_requests,
        bruteforce_window_ms=bruteforce_window_ms,
        bruteforce_login_attempt_limit=bruteforce_login_attempt_limit,
        bruteforce_ip_attempt_limit=bruteforce_ip_attempt_limit,
        bruteforce_block_ms=bruteforce_block_ms,
    )


_SETTINGS_CACHE: Settings | None = None


def get_settings(*, refresh: bool = False) -> Settings:
    global _SETTINGS_CACHE
    if refresh or _SETTINGS_CACHE is None:
        _SETTINGS_CACHE = load_settings()
    return _SETTINGS_CACHE
