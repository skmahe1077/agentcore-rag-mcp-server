"""check_operator_permissions: the authoritative allow/deny decision for a
requested action, re-derived from DynamoDB entitlements on every call.

This is the tool every other tool's authorization ultimately traces back to
- see security.resolve_entitlement. The model never grants access; it only
ever reports what this tool decided.
"""

from __future__ import annotations

from typing import Any

from app.mcp_server.clients import get_table
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import (
    CheckOperatorPermissionsInput,
    CheckOperatorPermissionsOutput,
)
from app.mcp_server.security import enforce_identity_binding, resolve_entitlement

logger = get_logger(__name__)

_WRITE_ACTIONS = {"write", "create_incident_record", "remediate", "change", "delete"}


def check_operator_permissions(
    payload: CheckOperatorPermissionsInput,
) -> CheckOperatorPermissionsOutput:
    entitlement = resolve_entitlement(payload.user_id, get_table())

    if not entitlement.found:
        reason = "unknown_user" if entitlement.role is None else "unrecognized_role"
        result = CheckOperatorPermissionsOutput(
            allowed=False,
            applied_role=entitlement.role,
            permitted_environments=[],
            permitted_tools=[],
            permitted_classifications=[],
            decision_reason=f"Denied: {reason} for user_id.",
        )
        log_with_fields(
            logger,
            20,
            "authorization_decision",
            allowed=False,
            reason=reason,
            user_id=payload.user_id,
        )
        return result

    environment_allowed = payload.environment.value in entitlement.permitted_environments
    is_write_action = payload.requested_action.lower() in _WRITE_ACTIONS
    write_allowed = (not is_write_action) or entitlement.can_write

    allowed = environment_allowed and write_allowed

    if not environment_allowed:
        reason = f"role '{entitlement.role}' is not permitted in environment '{payload.environment.value}'."
    elif not write_allowed:
        reason = f"role '{entitlement.role}' is read-only and cannot perform write action '{payload.requested_action}'."
    else:
        reason = f"role '{entitlement.role}' is permitted for '{payload.requested_action}' in '{payload.environment.value}'."

    result = CheckOperatorPermissionsOutput(
        allowed=allowed,
        applied_role=entitlement.role,
        permitted_environments=list(entitlement.permitted_environments),
        permitted_tools=list(entitlement.permitted_tools),
        permitted_classifications=list(entitlement.permitted_classifications),
        decision_reason=reason,
    )

    log_with_fields(
        logger,
        20,
        "authorization_decision",
        allowed=allowed,
        role=entitlement.role,
        environment=payload.environment.value,
        requested_action=payload.requested_action,
    )
    return result


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # `event` may be the tool arguments directly, or {"arguments": {...},
    # "requestContext": {...}} when invoked through AgentCore Gateway with
    # JWT passthrough - verify the exact envelope shape against the live
    # Gateway before production use (see README.md manual-verification steps).
    payload = CheckOperatorPermissionsInput.model_validate(event.get("arguments", event))
    set_correlation_id(payload.correlation_id)
    enforce_identity_binding(event, payload.user_id)
    return check_operator_permissions(payload).model_dump()
