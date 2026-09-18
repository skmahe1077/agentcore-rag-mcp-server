"""JWT validation for the agent.

In the deployed architecture, AgentCore Gateway's custom_jwt_authorizer
(terraform/agentcore.tf) validates every request's signature, issuer,
audience, and expiry before the agent or any MCP tool ever runs - AWS
performs that check, not this code. This module exists for two reasons:

1. Defense in depth: the agent independently re-validates the bearer token
   it receives before trusting any claim from it, rather than assuming the
   Gateway's decision reached it unmodified.
2. Local development: when running the agent outside AgentCore Runtime
   (e.g. against the demo client directly), there is no Gateway in front of
   it, so this is the only JWT validation that happens.

Either way, the *authorization* decision (what the caller may do) is never
made here or trusted from the token's role claim - it is always re-derived
from DynamoDB entitlements by user_id, in app/mcp_server/security.py. This
module only answers "is this a genuine, unexpired token for a known
issuer/audience, and who does it claim to be."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from app.mcp_server.security import AuthorizationError


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    claimed_role: str | None
    raw_claims: dict[str, Any]


_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(discovery_jwks_uri: str) -> PyJWKClient:
    client = _jwks_clients.get(discovery_jwks_uri)
    if client is None:
        client = PyJWKClient(discovery_jwks_uri, cache_keys=True, lifespan=300)
        _jwks_clients[discovery_jwks_uri] = client
    return client


def validate_jwt(
    token: str,
    *,
    jwks_uri: str,
    issuer: str,
    client_id: str,
) -> AuthenticatedUser:
    """Validate signature, issuer, and expiry; extract the caller's
    identity. Raises AuthorizationError on any failure - callers must not
    retry an AuthorizationError, per the project's reliability rules
    (authorization failures are never retried).

    Expects a Cognito *access* token, not an ID token: this project's demo
    client authenticates to AgentCore Runtime/Gateway with access tokens
    because AWS's custom_jwt_authorizer validates the token's `client_id`
    claim against allowed_clients (confirmed against the live API) - Cognito
    ID tokens don't carry a `client_id` claim (they carry `aud` instead), so
    only access tokens work here. Access tokens also don't carry custom
    attributes like custom:role - that's fine, since the authorization
    decision is never taken from this claim anyway (see module docstring).
    """
    if not token:
        raise AuthorizationError("Missing bearer token.")

    try:
        signing_key = _get_jwks_client(jwks_uri).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "iss", "sub", "client_id"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthorizationError(f"Invalid token: {exc}") from exc

    if claims.get("client_id") != client_id:
        raise AuthorizationError("Token's client_id does not match the expected app client.")

    user_id = claims.get("username") or claims.get("cognito:username") or claims.get("sub")
    if not user_id:
        raise AuthorizationError("Token is missing a user identity claim.")

    return AuthenticatedUser(
        user_id=str(user_id),
        claimed_role=claims.get("custom:role"),
        raw_claims=claims,
    )
