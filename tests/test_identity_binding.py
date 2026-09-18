"""enforce_identity_binding rejects a tool call whose arguments claim a
different user_id than the Gateway's own JWT-validated caller identity - a
model cannot request on behalf of a user_id it didn't authenticate as."""

from __future__ import annotations

import pytest

from app.mcp_server.security import AuthorizationError, enforce_identity_binding


def test_no_op_when_gateway_identity_absent():
    # Local/dev invocation with no requestContext - should not raise.
    enforce_identity_binding({}, "demo-incident-commander")


def test_passes_when_identities_match():
    event = {"requestContext": {"authorizer": {"claims": {"cognito:username": "demo-incident-commander"}}}}
    enforce_identity_binding(event, "demo-incident-commander")


def test_rejects_mismatched_identity():
    event = {"requestContext": {"authorizer": {"claims": {"cognito:username": "demo-read-only-operator"}}}}
    with pytest.raises(AuthorizationError):
        enforce_identity_binding(event, "demo-incident-commander")


def test_falls_back_to_sub_claim():
    event = {"requestContext": {"authorizer": {"claims": {"sub": "abc-123"}}}}
    with pytest.raises(AuthorizationError):
        enforce_identity_binding(event, "demo-incident-commander")
    enforce_identity_binding(event, "abc-123")


def test_lambda_handler_rejects_spoofed_user_id(dynamodb_table):
    from app.mcp_server.tools.check_operator_permissions import lambda_handler

    event = {
        "arguments": {
            "user_id": "demo-incident-commander",
            "environment": "production",
            "resource": "checkout",
            "requested_action": "read",
        },
        "requestContext": {"authorizer": {"claims": {"cognito:username": "demo-read-only-operator"}}},
    }

    with pytest.raises(AuthorizationError):
        lambda_handler(event, None)
