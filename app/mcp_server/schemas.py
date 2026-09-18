"""Strict Pydantic input/output schemas for every MCP tool.

`model_config = ConfigDict(extra="forbid")` on every model rejects unknown
fields rather than silently ignoring them - part of the strict JSON-schema
validation required at the tool boundary.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp_server.security import (
    ALLOWED_RESOURCE_TYPES,
    MAX_COMMENTS_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_STRING_LENGTH,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Environment(StrEnum):
    production = "production"
    staging = "staging"


class Severity(StrEnum):
    sev1 = "SEV1"
    sev2 = "SEV2"
    sev3 = "SEV3"
    sev4 = "SEV4"


class ResourceType(StrEnum):
    application_load_balancer = "application_load_balancer"
    target_group = "target_group"
    ec2_instance = "ec2_instance"
    auto_scaling_group = "auto_scaling_group"
    lambda_function = "lambda_function"
    rds_database = "rds_database"


# Every tool takes a flat user_id: str rather than a nested user_context
# object. AgentCore Gateway's tool-schema format can't express nested
# object properties (confirmed against the live API - see
# terraform/agentcore.tf), so a model calling a nested user_context.user_id
# parameter has no visibility into its shape and will not reliably produce
# it (confirmed live: the model flattened it into a sibling user_id field
# instead). Only user_id is trusted as an authorization input in any case -
# every tool re-verifies it against DynamoDB entitlements
# (security.resolve_entitlement) rather than trusting any role/permission
# claim.
#
# correlation_id is optional and carries no authorization weight - it exists
# solely so each tool's lambda_handler can call
# logging_config.set_correlation_id() and tie its structured logs back to
# the agent invocation that made the call (see OBSERVABILITY.md's
# "Viewing a single investigation end-to-end" Logs Insights query, which
# otherwise has no way to reach the Lambda tool log groups: confirmed live
# that without this field every tool log line carried
# "correlation_id": null).

# ---------------------------------------------------------------------------
# check_operator_permissions
# ---------------------------------------------------------------------------


class CheckOperatorPermissionsInput(_StrictModel):
    user_id: str = Field(min_length=1, max_length=200)
    environment: Environment
    resource: str = Field(min_length=1, max_length=MAX_STRING_LENGTH)
    requested_action: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(default="", max_length=64)


class CheckOperatorPermissionsOutput(_StrictModel):
    allowed: bool
    applied_role: str | None
    permitted_environments: list[str]
    permitted_tools: list[str]
    permitted_classifications: list[str]
    decision_reason: str


# ---------------------------------------------------------------------------
# search_runbooks
# ---------------------------------------------------------------------------


class SearchRunbooksInput(_StrictModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    service: str = Field(min_length=1, max_length=200)
    environment: Environment
    severity: Severity
    max_results: int = Field(default=4, ge=1, le=10)
    user_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(default="", max_length=64)


class RetrievedPassage(_StrictModel):
    document_id: str
    title: str
    version: int
    excerpt: str
    score: float
    classification: str
    source_uri: str


class SearchRunbooksOutput(_StrictModel):
    retrieved_passages: list[RetrievedPassage]
    relevance_scores: list[float]
    document_metadata: list[dict[str, Any]]
    citations: list[str]
    version_information: list[str]
    authorization_decision: str


# ---------------------------------------------------------------------------
# get_alarm_details
# ---------------------------------------------------------------------------


class GetAlarmDetailsInput(_StrictModel):
    alarm_name: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=30)
    user_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(default="", max_length=64)


class GetAlarmDetailsOutput(_StrictModel):
    alarm_state: str
    metric: str
    threshold: float
    evaluation_period: int
    state_reason: str
    transition_time: str
    dimensions: dict[str, str]
    simulated: bool


# ---------------------------------------------------------------------------
# get_resource_status
# ---------------------------------------------------------------------------


class GetResourceStatusInput(_StrictModel):
    resource_type: ResourceType
    resource_identifier: str = Field(min_length=1, max_length=300)
    region: str = Field(min_length=1, max_length=30)
    user_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(default="", max_length=64)

    @field_validator("resource_type")
    @classmethod
    def _allow_listed(cls, value: ResourceType) -> ResourceType:
        if value.value not in ALLOWED_RESOURCE_TYPES:
            raise ValueError("resource_type is not in the allow-list.")
        return value


class GetResourceStatusOutput(_StrictModel):
    resource_type: str
    resource_identifier: str
    state: str
    fields: dict[str, Any]
    simulated: bool


# ---------------------------------------------------------------------------
# get_recent_events
# ---------------------------------------------------------------------------


class GetRecentEventsInput(_StrictModel):
    service: str = Field(min_length=1, max_length=200)
    environment: Environment
    start_time: str = Field(min_length=1, max_length=40)
    end_time: str = Field(min_length=1, max_length=40)
    user_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(default="", max_length=64)


class OperationalEvent(_StrictModel):
    event_type: str
    description: str
    timestamp: str
    source: str
    simulated: bool


class GetRecentEventsOutput(_StrictModel):
    events: list[OperationalEvent]
    simulated: bool


# ---------------------------------------------------------------------------
# create_incident_record
# ---------------------------------------------------------------------------


class CreateIncidentRecordInput(_StrictModel):
    title: str = Field(min_length=1, max_length=200)
    severity: Severity
    affected_service: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=MAX_STRING_LENGTH)
    evidence: dict[str, Any]
    confirmed_by_user: bool
    idempotency_key: str = Field(min_length=1, max_length=200)
    user_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(default="", max_length=64)


class CreateIncidentRecordOutput(_StrictModel):
    incident_id: str
    status: str


# ---------------------------------------------------------------------------
# submit_feedback
# ---------------------------------------------------------------------------


class SubmitFeedbackInput(_StrictModel):
    session_id: str = Field(min_length=1, max_length=200)
    rating: int = Field(ge=1, le=5)
    comments: str = Field(default="", max_length=MAX_COMMENTS_LENGTH)
    correlation_id: str = Field(default="", max_length=64)


class SubmitFeedbackOutput(_StrictModel):
    status: str
