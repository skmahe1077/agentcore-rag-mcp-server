"""Tests for app.agent.authorization: JWT signature, issuer, client_id, and
expiry validation (defense-in-depth behind AgentCore Runtime/Gateway's own
custom_jwt_authorizer - see terraform/agentcore.tf).

Tokens here are shaped like real Cognito *access* tokens (client_id,
username, token_use=access - no aud, no custom:role), matching what
AgentCore's authorizer actually validates and what app/client/demo_client.py
sends - confirmed against a live deployment (see TROUBLESHOOTING.md)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.agent.authorization import validate_jwt
from app.mcp_server.security import AuthorizationError

ISSUER = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_testpool"
CLIENT_ID = "test-client-id"
JWKS_URI = f"{ISSUER}/.well-known/jwks.json"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(
    rsa_key,
    *,
    issuer=ISSUER,
    client_id=CLIENT_ID,
    exp_delta=3600,
    sub="abc-123",
    username="demo-incident-commander",
):
    now = int(time.time())
    claims = {
        "sub": sub,
        "username": username,
        "client_id": client_id,
        "token_use": "access",
        "iss": issuer,
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(claims, rsa_key, algorithm="RS256")


def _patched_jwks(rsa_key):
    mock_signing_key = MagicMock()
    mock_signing_key.key = rsa_key.public_key()
    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
    return patch("app.agent.authorization._get_jwks_client", return_value=mock_client)


def test_valid_token_is_accepted(rsa_key):
    token = _make_token(rsa_key)
    with _patched_jwks(rsa_key):
        user = validate_jwt(token, jwks_uri=JWKS_URI, issuer=ISSUER, client_id=CLIENT_ID)

    assert user.user_id == "demo-incident-commander"
    assert user.claimed_role is None  # access tokens don't carry custom:role


def test_expired_token_is_rejected(rsa_key):
    token = _make_token(rsa_key, exp_delta=-3600)
    with _patched_jwks(rsa_key), pytest.raises(AuthorizationError):
        validate_jwt(token, jwks_uri=JWKS_URI, issuer=ISSUER, client_id=CLIENT_ID)


def test_wrong_client_id_is_rejected(rsa_key):
    token = _make_token(rsa_key, client_id="some-other-client")
    with _patched_jwks(rsa_key), pytest.raises(AuthorizationError):
        validate_jwt(token, jwks_uri=JWKS_URI, issuer=ISSUER, client_id=CLIENT_ID)


def test_wrong_issuer_is_rejected(rsa_key):
    token = _make_token(rsa_key, issuer="https://evil.example.com")
    with _patched_jwks(rsa_key), pytest.raises(AuthorizationError):
        validate_jwt(token, jwks_uri=JWKS_URI, issuer=ISSUER, client_id=CLIENT_ID)


def test_missing_token_is_rejected():
    with pytest.raises(AuthorizationError):
        validate_jwt("", jwks_uri=JWKS_URI, issuer=ISSUER, client_id=CLIENT_ID)


def test_tampered_signature_is_rejected(rsa_key):
    token = _make_token(rsa_key)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with _patched_jwks(rsa_key), pytest.raises(AuthorizationError):
        validate_jwt(tampered, jwks_uri=JWKS_URI, issuer=ISSUER, client_id=CLIENT_ID)
