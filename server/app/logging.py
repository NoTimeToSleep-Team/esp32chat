from __future__ import annotations

import logging
import logging.config
import re

from app.config import Settings


_SECRET_QUERY = re.compile(
    r"(?i)(session_token|access_token|token|password|secret|authorization)=([^&\s,;]+)"
)
_SECRET_PATH = re.compile(r"(?i)(/auth/session/)[A-Za-z0-9._~-]{8,}")


def _redact_text(value: str) -> str:
    redacted = _SECRET_QUERY.sub(lambda match: f"{match.group(1)}=[redacted]", value)
    return _SECRET_PATH.sub(r"\1[redacted]", redacted)


class RedactSecretsFilter(logging.Filter):
    """Keep tokens out of access logs and any other log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _redact_text(item) if isinstance(item, str) else item
                for item in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_text(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


def configure_logging(settings: Settings) -> None:
    level = settings.log_level.upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "redact_secrets": {
                    "()": "app.logging.RedactSecretsFilter",
                }
            },
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                    "filters": ["redact_secrets"],
                }
            },
            "root": {
                "handlers": ["console"],
                "level": level,
            },
            "loggers": {
                "uvicorn.error": {
                    "level": level,
                    "propagate": True,
                },
                "uvicorn.access": {
                    "level": level,
                    "propagate": True,
                },
            },
        }
    )


def install_runtime_log_filters() -> None:
    """Attach redaction after uvicorn has installed its own handlers.

    Uvicorn configures access logging after importing the ASGI application, so
    the dictConfig filter alone is not enough for ``uvicorn.access``.
    """
    redact = RedactSecretsFilter()
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        logger = logging.getLogger(name)
        logger.addFilter(redact)
        for handler in logger.handlers:
            handler.addFilter(redact)
    root = logging.getLogger()
    root.addFilter(redact)
    for handler in root.handlers:
        handler.addFilter(redact)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
