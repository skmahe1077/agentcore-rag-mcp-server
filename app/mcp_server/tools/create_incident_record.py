"""create_incident_record: the only write tool in this system, and only
ever after explicit human confirmation.

Refuses unconfirmed requests before touching any other check. Verifies the
caller's role can write (re-derived from DynamoDB, never trusted from the
model). Prevents duplicate creation via an idempotency record. No automated
remediation happens here or anywhere else in this version of the system -
this tool only records an incident; a human executes any resulting change
through existing tooling, per emergency-change-procedure.md.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.mcp_server.clients import get_table, to_dynamodb_safe
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import CreateIncidentRecordInput, CreateIncidentRecordOutput
from app.mcp_server.security import (
    AuthorizationError,
    enforce_identity_binding,
    redact_value,
    resolve_entitlement,
    validate_evidence_size,
)

logger = get_logger(__name__)

IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


def create_incident_record(
    payload: CreateIncidentRecordInput,
) -> CreateIncidentRecordOutput:
    if not payload.confirmed_by_user:
        log_with_fields(logger, 30, "incident_creation_refused", reason="not_confirmed")
        raise AuthorizationError("Refused: create_incident_record requires confirmed_by_user=true.")

    table = get_table()
    entitlement = resolve_entitlement(payload.user_id, table)
    if not entitlement.found or not entitlement.can_write:
        log_with_fields(
            logger,
            30,
            "incident_creation_refused",
            reason="not_write_capable",
            role=entitlement.role,
        )
        raise AuthorizationError(f"Refused: role '{entitlement.role}' is not authorized to create incident records.")

    validate_evidence_size(payload.evidence)

    idempotency_key = f"IDEMPOTENCY#{payload.idempotency_key}"
    existing = table.get_item(Key={"pk": idempotency_key, "sk": idempotency_key}).get("Item")
    if existing:
        log_with_fields(
            logger,
            20,
            "incident_creation_deduplicated",
            incident_id=existing.get("incident_id"),
        )
        return CreateIncidentRecordOutput(incident_id=existing["incident_id"], status="duplicate_prevented")

    incident_id = f"INC-{uuid.uuid4().hex[:10].upper()}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    redacted_evidence = redact_value(payload.evidence)
    redacted_summary = redact_value(payload.summary)

    table.put_item(
        Item={
            "pk": f"INCIDENT#{incident_id}",
            "sk": f"INCIDENT#{incident_id}",
            "gsi1pk": "INCIDENT",
            "gsi1sk": f"{created_at}#{incident_id}",
            "entity_type": "incident",
            "incident_id": incident_id,
            "title": payload.title,
            "severity": payload.severity.value,
            "affected_service": payload.affected_service,
            "summary": redacted_summary,
            "evidence": to_dynamodb_safe(redacted_evidence),
            "created_by": payload.user_id,
            "created_by_role": entitlement.role,
            "created_at": created_at,
            "status": "open",
        }
    )

    table.put_item(
        Item={
            "pk": idempotency_key,
            "sk": idempotency_key,
            "entity_type": "idempotency",
            "incident_id": incident_id,
            "ttl": int(time.time()) + IDEMPOTENCY_TTL_SECONDS,
        }
    )

    log_with_fields(
        logger,
        20,
        "incident_created",
        incident_id=incident_id,
        created_by=payload.user_id,
        role=entitlement.role,
        severity=payload.severity.value,
    )

    return CreateIncidentRecordOutput(incident_id=incident_id, status="created")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = CreateIncidentRecordInput.model_validate(event.get("arguments", event))
    set_correlation_id(payload.correlation_id)
    enforce_identity_binding(event, payload.user_id)
    return create_incident_record(payload).model_dump()
