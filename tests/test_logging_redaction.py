"""Sensitive values must never appear in log output (#15)."""

from __future__ import annotations

import io
import json
import logging

from app.mcp_server.logging_config import _JsonFormatter, log_with_fields


def _capture_log(fields: dict) -> str:
    logger = logging.getLogger("test_logging_redaction")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)

    log_with_fields(logger, logging.INFO, "test_event", **fields)
    return stream.getvalue()


def test_authorization_header_field_is_redacted():
    output = _capture_log({"authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature"})
    payload = json.loads(output)
    assert payload["authorization"] == "***REDACTED***"
    assert "eyJhbGciOiJSUzI1NiJ9" not in output


def test_jwt_like_value_is_redacted_even_without_a_sensitive_field_name():
    output = _capture_log({"note": "token was eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefghij1234567890"})
    assert "eyJhbGciOiJSUzI1NiJ9" not in output


def test_aws_access_key_is_redacted():
    output = _capture_log({"note": "used AKIAABCDEFGHIJKLMNOP to sign"})
    assert "AKIAABCDEFGHIJKLMNOP" not in output
    assert "REDACTED_AWS_KEY" in output


def test_prompt_field_is_redacted():
    output = _capture_log({"prompt": "the full system prompt and conversation history"})
    payload = json.loads(output)
    assert payload["prompt"] == "***REDACTED***"


def test_ordinary_fields_pass_through_unredacted():
    output = _capture_log({"tool": "search_runbooks", "result_count": 3})
    payload = json.loads(output)
    assert payload["tool"] == "search_runbooks"
    assert payload["result_count"] == 3
