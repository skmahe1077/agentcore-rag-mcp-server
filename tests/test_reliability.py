"""Reliability rules: MCP calls have bounded timeouts and bounded retries
(#12), and authorization/validation failures are never retried."""

from __future__ import annotations

import inspect

from app.mcp_server.clients import _BOTO_CONFIG
from app.mcp_server.security import AuthorizationError, ValidationError


def test_boto_clients_have_bounded_connect_and_read_timeouts():
    # A stalled dependency must fail fast, not hang the tool call
    # indefinitely and exhaust the agent's overall tool-call budget.
    assert _BOTO_CONFIG.connect_timeout is not None
    assert _BOTO_CONFIG.connect_timeout <= 10
    assert _BOTO_CONFIG.read_timeout is not None
    assert _BOTO_CONFIG.read_timeout <= 30


def test_boto_clients_use_bounded_adaptive_retries():
    assert _BOTO_CONFIG.retries["max_attempts"] <= 5
    assert _BOTO_CONFIG.retries["mode"] == "adaptive"


def test_authorization_and_validation_errors_are_not_retryable_exceptions():
    # These exception types exist specifically so callers can distinguish
    # "don't retry this" outcomes from transient failures. Asserting they
    # are plain, undecorated exceptions (no retry metadata/backoff wrapper)
    # documents that contract at the type level.
    for exc_type in (AuthorizationError, ValidationError):
        assert issubclass(exc_type, Exception)
        assert not hasattr(exc_type, "retry_after")


def test_lambda_tool_handlers_do_not_catch_and_retry_authorization_errors():
    from app.mcp_server.tools import create_incident_record

    source = inspect.getsource(create_incident_record)
    # The tool must let AuthorizationError propagate to the caller (Gateway
    # returns it as a tool error) rather than swallowing and retrying it.
    assert "except AuthorizationError" not in source
