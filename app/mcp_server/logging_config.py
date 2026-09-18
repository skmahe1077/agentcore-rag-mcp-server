"""Structured JSON logging with correlation-ID propagation and redaction.

Every log record is a single JSON object so CloudWatch Logs Insights can
query it without a custom parser. Sensitive fields are redacted at the
logging boundary, not left to callers to remember to scrub.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

from app.mcp_server.security import redact_value

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

# Field names that must never appear unredacted in a log record, regardless
# of where they came from in the call.
_SENSITIVE_FIELDS = {
    "authorization",
    "jwt",
    "token",
    "access_token",
    "id_token",
    "refresh_token",
    "password",
    "secret",
    "api_key",
    "prompt",
    "full_prompt",
}


def set_correlation_id(correlation_id: str) -> None:
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key.lower() in _SENSITIVE_FIELDS:
                    payload[key] = "***REDACTED***"
                else:
                    payload[key] = redact_value(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    from app.mcp_server.config import get_settings

    logger.setLevel(logging.DEBUG if get_settings().enable_debug_logging else logging.INFO)
    return logger


def log_with_fields(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": fields})
