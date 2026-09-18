"""Demo-client authentication: exchanges a demo user's Cognito username and
password for a bearer access token, using the Cognito app client's
USER_PASSWORD_AUTH flow (terraform/cognito.tf). No AWS credentials are
required for this step - only network access and the user's own password -
matching how a real end user would authenticate to this system.
"""

from __future__ import annotations

import boto3


def get_access_token(*, user_id: str, password: str, client_id: str, region: str) -> str:
    """Returns a Cognito *access* token (not an ID token). AgentCore's
    custom_jwt_authorizer validates the token's client_id claim against
    allowed_clients (confirmed against a live deployment - see
    TROUBLESHOOTING.md); Cognito ID tokens carry an aud claim instead of
    client_id, so only access tokens work for calling AgentCore
    Runtime/Gateway. Raises botocore.exceptions.ClientError on
    authentication failure - callers should not retry that, per the
    project's reliability rules (authentication/authorization failures are
    never retried)."""
    client = boto3.client("cognito-idp", region_name=region)
    response = client.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": user_id, "PASSWORD": password},
        ClientId=client_id,
    )
    return response["AuthenticationResult"]["AccessToken"]
