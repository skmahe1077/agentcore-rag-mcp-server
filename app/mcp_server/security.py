"""Shared security primitives for every MCP tool: input-size limits,
redaction, and authorization resolution.

Authorization is always re-derived here from the entitlements stored in
DynamoDB, keyed by user_id - never trusted from a role string the caller
(including the model) supplies. See ARCHITECTURE.md and SECURITY.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MAX_STRING_LENGTH = 2000
MAX_QUERY_LENGTH = 500
MAX_EVIDENCE_BYTES = 8192
MAX_COMMENTS_LENGTH = 1000

KNOWN_ROLES = frozenset(
    {
        "cloud_engineer",
        "incident_commander",
        "application_engineer",
        "read_only_operator",
        "administrator",
    }
)

WRITE_CAPABLE_ROLES = frozenset({"incident_commander", "administrator"})

ALLOWED_RESOURCE_TYPES = frozenset(
    {
        "application_load_balancer",
        "target_group",
        "ec2_instance",
        "auto_scaling_group",
        "lambda_function",
        "rds_database",
    }
)


class ValidationError(Exception):
    """A request failed input validation. Never retried automatically."""


class AuthorizationError(Exception):
    """A request was denied by an authorization check. Never retried automatically."""


_JWT_LIKE = re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_AWS_ACCESS_KEY = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")
_LONG_TOKEN_LIKE = re.compile(r"\b[A-Za-z0-9+/_-]{40,}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact_text(text: str) -> str:
    """Mask JWT-like, AWS-access-key-like, long-token-like, and email
    substrings in free text before it is logged or stored."""
    text = _JWT_LIKE.sub("***REDACTED_TOKEN***", text)
    text = _AWS_ACCESS_KEY.sub("***REDACTED_AWS_KEY***", text)
    text = _LONG_TOKEN_LIKE.sub("***REDACTED_TOKEN***", text)
    text = _EMAIL.sub("***REDACTED_EMAIL***", text)
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    return value


def validate_length(value: str, max_length: int, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string.")
    if len(value) == 0:
        raise ValidationError(f"{field_name} must not be empty.")
    if len(value) > max_length:
        raise ValidationError(f"{field_name} exceeds the maximum length of {max_length} characters.")
    return value


def validate_evidence_size(evidence: Any) -> None:
    import json

    encoded = json.dumps(evidence, default=str)
    if len(encoded.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise ValidationError(f"evidence exceeds the maximum size of {MAX_EVIDENCE_BYTES} bytes.")


@dataclass(frozen=True)
class Entitlement:
    user_id: str
    role: str | None
    permitted_environments: tuple[str, ...]
    permitted_tools: tuple[str, ...]
    permitted_classifications: tuple[str, ...]
    can_write: bool
    found: bool


def extract_gateway_authenticated_user_id(event: dict[str, Any]) -> str | None:
    """Read the caller identity AgentCore Gateway injects into the Lambda
    invocation event after its own custom_jwt_authorizer has validated the
    bearer token (JWT passthrough - see terraform/agentcore.tf's gateway
    credential_provider_configuration). Returns None when absent, e.g. for
    direct/local invocations outside the Gateway."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    # "username" for Cognito access tokens (what this project's clients
    # actually send - see app/client/auth.py), "cognito:username" for ID
    # tokens, "sub" as a last-resort fallback.
    return claims.get("username") or claims.get("cognito:username") or claims.get("sub")


def enforce_identity_binding(event: dict[str, Any], claimed_user_id: str) -> None:
    """If the Gateway supplied an authenticated identity, it must match the
    user_id the tool call's own arguments claim - the model can request on
    behalf of a user_id, but cannot make that request *as* a different
    user_id than the one who actually authenticated. Raises
    AuthorizationError on a mismatch; a no-op when the Gateway did not
    inject an identity (local/dev invocation)."""
    authenticated_user_id = extract_gateway_authenticated_user_id(event)
    if authenticated_user_id is not None and authenticated_user_id != claimed_user_id:
        raise AuthorizationError(
            f"Identity mismatch: authenticated caller '{authenticated_user_id}' does not match "
            f"the user_id '{claimed_user_id}' supplied in the tool call arguments."
        )


def resolve_entitlement(user_id: str, table: Any) -> Entitlement:
    """Look up the caller's role by user_id, then the role's entitlements.
    Both lookups happen fresh on every call - a stale or forged role claim
    in the caller's own context is never trusted."""
    if not user_id:
        return Entitlement(
            user_id="",
            role=None,
            permitted_environments=(),
            permitted_tools=(),
            permitted_classifications=(),
            can_write=False,
            found=False,
        )

    user_item = table.get_item(Key={"pk": f"USER#{user_id}", "sk": f"USER#{user_id}"}).get("Item")
    if not user_item:
        return Entitlement(
            user_id=user_id,
            role=None,
            permitted_environments=(),
            permitted_tools=(),
            permitted_classifications=(),
            can_write=False,
            found=False,
        )

    role = user_item.get("role")
    if role not in KNOWN_ROLES:
        return Entitlement(
            user_id=user_id,
            role=role,
            permitted_environments=(),
            permitted_tools=(),
            permitted_classifications=(),
            can_write=False,
            found=False,
        )

    entitlement_item = table.get_item(Key={"pk": f"ENTITLEMENT#{role}", "sk": f"ENTITLEMENT#{role}"}).get("Item")
    if not entitlement_item:
        return Entitlement(
            user_id=user_id,
            role=role,
            permitted_environments=(),
            permitted_tools=(),
            permitted_classifications=(),
            can_write=False,
            found=False,
        )

    return Entitlement(
        user_id=user_id,
        role=role,
        permitted_environments=tuple(entitlement_item.get("permitted_environments", [])),
        permitted_tools=tuple(entitlement_item.get("permitted_tools", [])),
        permitted_classifications=tuple(entitlement_item.get("permitted_classifications", [])),
        can_write=bool(entitlement_item.get("can_write", False)),
        found=True,
    )
