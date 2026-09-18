#!/usr/bin/env python3
"""Authenticated demo client: invokes the deployed AgentCore Runtime with
one of the four demo scenarios (see DEMO.md) and prints a formatted
result, including the observability fields useful for the demo (Demo 4).

Usage:
    python3 -m app.client.demo_client \\
        --agent-runtime-arn <arn> --region eu-west-1 \\
        --user-id demo-incident-commander --password <password> \\
        --cognito-client-id <client-id> \\
        --incident-description "The production checkout service is returning HTTP 5xx errors. Help me investigate using the approved runbook." \\
        --service checkout --environment production --severity SEV2

Never pass --password on a shared shell history; scripts/get_demo_token.sh
writes credentials to a local, gitignored file instead of your terminal.
"""

from __future__ import annotations

import argparse
import time
import urllib.parse
import uuid

import requests

from app.client.auth import get_access_token

# AgentCore Runtime is configured for JWT (not IAM SigV4) inbound auth
# (terraform/agentcore.tf) - confirmed against a live deployment that boto3's
# generated invoke_agent_runtime client cannot carry a bearer token (its
# SigV4 signer always overwrites any manually-set Authorization header, and
# IAM SigV4 + JWT inbound auth are mutually exclusive on one runtime). A
# direct HTTPS call is required instead - see TROUBLESHOOTING.md.
#
# The platform's own custom_jwt_authorizer validates the standard
# Authorization header and then *consumes* it - confirmed live that it does
# not forward that header, or any other custom header, into the container
# for a direct client invocation. The request body is not filtered, so the
# same bearer token also goes in the JSON payload as "bearer_token" -
# app/agent/main.py's handler reads it from there and independently
# re-validates it (the token is a signed JWT, so this is still a
# cryptographic identity check, not a trust-the-caller shortcut).


def invoke(
    *,
    agent_runtime_arn: str,
    region: str,
    bearer_token: str,
    incident_description: str,
    service: str,
    environment: str,
    severity: str,
    correlation_id: str | None = None,
) -> dict:
    # AgentCore Runtime requires runtimeSessionId to be at least 33
    # characters (confirmed against the live API); uuid4().hex is exactly
    # 32, so use the full hyphenated UUID string form (36 chars) instead.
    session_id = correlation_id or str(uuid.uuid4())

    encoded_arn = urllib.parse.quote(agent_runtime_arn, safe="")
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    payload = {
        "incident_description": incident_description,
        "service": service,
        "environment": environment,
        "severity": severity,
        "correlation_id": session_id,
        "bearer_token": bearer_token,
    }

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    start = time.monotonic()
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    duration = time.monotonic() - start
    response.raise_for_status()

    return {
        "correlation_id": session_id,
        "client_observed_latency_seconds": round(duration, 3),
        "status_code": response.status_code,
        "result": response.json(),
    }


def _print_result(envelope: dict) -> None:
    result = envelope["result"]
    print(f"\nCorrelation ID: {envelope['correlation_id']}")
    print(f"Client-observed latency: {envelope['client_observed_latency_seconds']}s\n")

    if result.get("refused"):
        print("REFUSED:", result.get("refusal_reason"))
        return

    print("Observations:")
    for obs in result.get("observations", []):
        print(f"  - {obs['fact']}  (source: {obs['source_tool']})")

    print("\nPossible causes:")
    for cause in result.get("possible_causes", []):
        print(f"  - {cause}")

    print("\nRecommendations:")
    for rec in result.get("recommendations", []):
        print(f"  - {rec}")

    if result.get("assumptions"):
        print("\nAssumptions:")
        for a in result["assumptions"]:
            print(f"  - {a}")

    print("\nCitations:")
    for c in result.get("citations", []):
        print(f"  - {c}")

    print(f"\nSimulated evidence used: {result.get('simulated_evidence_used')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent-runtime-arn", required=True)
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--cognito-client-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument(
        "--password",
        required=True,
        help="Prefer piping this in; avoid literal shell args in shared history.",
    )
    parser.add_argument("--incident-description", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--environment", required=True, choices=["production", "staging"])
    parser.add_argument("--severity", required=True, choices=["SEV1", "SEV2", "SEV3", "SEV4"])
    args = parser.parse_args()

    bearer_token = get_access_token(
        user_id=args.user_id,
        password=args.password,
        client_id=args.cognito_client_id,
        region=args.region,
    )

    envelope = invoke(
        agent_runtime_arn=args.agent_runtime_arn,
        region=args.region,
        bearer_token=bearer_token,
        incident_description=args.incident_description,
        service=args.service,
        environment=args.environment,
        severity=args.severity,
    )
    _print_result(envelope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
