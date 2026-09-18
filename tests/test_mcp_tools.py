"""Unit tests for MCP tool business logic against a moto-mocked DynamoDB
table. Covers authorization, write-confirmation, idempotency, and simulated
evidence - see also tests/test_authorization.py and tests/test_retrieval.py
for the Bedrock-retrieval-specific and JWT-specific cases."""

from __future__ import annotations

import pytest

from app.mcp_server.schemas import (
    CheckOperatorPermissionsInput,
    CreateIncidentRecordInput,
    GetAlarmDetailsInput,
    GetRecentEventsInput,
    GetResourceStatusInput,
    SubmitFeedbackInput,
)
from app.mcp_server.security import AuthorizationError


def test_read_only_operator_denied_write(dynamodb_table):
    from app.mcp_server.tools.check_operator_permissions import (
        check_operator_permissions,
    )

    result = check_operator_permissions(
        CheckOperatorPermissionsInput(
            user_id="demo-read-only-operator",
            environment="production",
            resource="checkout",
            requested_action="write",
        )
    )
    assert result.allowed is False
    assert result.applied_role == "read_only_operator"


def test_incident_commander_allowed_write(dynamodb_table):
    from app.mcp_server.tools.check_operator_permissions import (
        check_operator_permissions,
    )

    result = check_operator_permissions(
        CheckOperatorPermissionsInput(
            user_id="demo-incident-commander",
            environment="production",
            resource="checkout",
            requested_action="create_incident_record",
        )
    )
    assert result.allowed is True


def test_unknown_user_denied(dynamodb_table):
    from app.mcp_server.tools.check_operator_permissions import (
        check_operator_permissions,
    )

    result = check_operator_permissions(
        CheckOperatorPermissionsInput(
            user_id="nobody",
            environment="production",
            resource="checkout",
            requested_action="read",
        )
    )
    assert result.allowed is False
    assert "unknown_user" in result.decision_reason


def test_create_incident_requires_confirmation(dynamodb_table):
    from app.mcp_server.tools.create_incident_record import create_incident_record

    with pytest.raises(AuthorizationError):
        create_incident_record(
            CreateIncidentRecordInput(
                title="Checkout 5xx",
                severity="SEV2",
                affected_service="checkout",
                summary="Elevated 5xx rate.",
                evidence={},
                confirmed_by_user=False,
                idempotency_key="k1",
                user_id="demo-incident-commander",
            )
        )


def test_create_incident_requires_write_capable_role(dynamodb_table):
    from app.mcp_server.tools.create_incident_record import create_incident_record

    with pytest.raises(AuthorizationError):
        create_incident_record(
            CreateIncidentRecordInput(
                title="Checkout 5xx",
                severity="SEV2",
                affected_service="checkout",
                summary="Elevated 5xx rate.",
                evidence={},
                confirmed_by_user=True,
                idempotency_key="k2",
                user_id="demo-read-only-operator",
            )
        )


def test_create_incident_succeeds_when_confirmed_and_authorized(dynamodb_table):
    from app.mcp_server.tools.create_incident_record import create_incident_record

    result = create_incident_record(
        CreateIncidentRecordInput(
            title="Checkout 5xx",
            severity="SEV2",
            affected_service="checkout",
            summary="Elevated 5xx rate, correlated with recent deployment.",
            evidence={"alarm": "checkout-http-5xx-high"},
            confirmed_by_user=True,
            idempotency_key="k3",
            user_id="demo-incident-commander",
        )
    )
    assert result.status == "created"
    assert result.incident_id.startswith("INC-")


def test_duplicate_incident_creation_is_prevented(dynamodb_table):
    from app.mcp_server.tools.create_incident_record import create_incident_record

    kwargs = {
        "title": "Checkout 5xx",
        "severity": "SEV2",
        "affected_service": "checkout",
        "summary": "Elevated 5xx rate.",
        "evidence": {},
        "confirmed_by_user": True,
        "idempotency_key": "k4",
        "user_id": "demo-incident-commander",
    }
    first = create_incident_record(CreateIncidentRecordInput(**kwargs))
    second = create_incident_record(CreateIncidentRecordInput(**kwargs))

    assert first.status == "created"
    assert second.status == "duplicate_prevented"
    assert second.incident_id == first.incident_id


def test_get_alarm_details_returns_simulated_evidence(dynamodb_table):
    from app.mcp_server.tools.get_alarm_details import get_alarm_details

    result = get_alarm_details(
        GetAlarmDetailsInput(
            alarm_name="checkout-http-5xx-high",
            region="eu-west-1",
            user_id="demo-incident-commander",
        )
    )
    assert result.simulated is True
    assert result.alarm_state == "ALARM"


def test_get_resource_status_rejects_disallowed_resource_type():
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        GetResourceStatusInput(
            resource_type="s3_bucket",  # not in the allow-list
            resource_identifier="anything",
            region="eu-west-1",
            user_id="demo-incident-commander",
        )


def test_get_resource_status_returns_simulated_fields(dynamodb_table):
    from app.mcp_server.tools.get_resource_status import get_resource_status

    result = get_resource_status(
        GetResourceStatusInput(
            resource_type="target_group",
            resource_identifier="checkout-tg",
            region="eu-west-1",
            user_id="demo-incident-commander",
        )
    )
    assert result.simulated is True
    assert result.fields["unhealthy_targets"] == 2


def test_get_recent_events_is_bounded_and_simulated(dynamodb_table):
    from app.mcp_server.tools.get_recent_events import get_recent_events

    result = get_recent_events(
        GetRecentEventsInput(
            service="checkout",
            environment="production",
            start_time="2026-09-18T00:00:00Z",
            end_time="2026-09-18T23:59:59Z",
            user_id="demo-incident-commander",
        )
    )
    assert result.simulated is True
    assert 0 < len(result.events) <= 20


def test_submit_feedback_redacts_token_like_content(dynamodb_table):
    from app.mcp_server.tools.submit_feedback import submit_feedback

    result = submit_feedback(
        SubmitFeedbackInput(
            session_id="sess-1",
            rating=5,
            comments="Token was ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD, still helpful",
        )
    )
    assert result.status == "recorded"

    feedback_sk = next(i["sk"] for i in dynamodb_table.scan()["Items"] if i.get("session_id") == "sess-1")
    stored = dynamodb_table.get_item(Key={"pk": "FEEDBACK#sess-1", "sk": feedback_sk})["Item"]
    assert "ghp_" not in stored["comments"]
    assert "REDACTED" in stored["comments"]
