"""The Cloud Operations Runbook Agent: connects to AgentCore Gateway for
MCP tool discovery, runs a bounded investigation using a configurable
Bedrock foundation model, and returns a grounded, cited, structured result.

Two entry points:
  - `invoke_agent(...)`: the reusable orchestration function, used by both
    the AgentCore Runtime entrypoint below and app/client/demo_client.py
    when driving the agent directly for local development.
  - `handler(payload, context)`: the AgentCore Runtime entrypoint
    (bedrock_agentcore.runtime.BedrockAgentCoreApp), invoked per request by
    the managed runtime.
"""

from __future__ import annotations

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.runtime.context import RequestContext
from botocore.config import Config
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands.types.agent import Limits

from app.agent.authorization import AuthenticatedUser, validate_jwt
from app.agent.configuration import AgentConfiguration, get_agent_configuration
from app.agent.incident_analysis import IncidentInvestigationResult
from app.agent.observability import (
    InvocationMetrics,
    ToolCallLimiter,
    finish_invocation,
    should_sample_trace,
    start_invocation,
)
from app.agent.prompts import SYSTEM_PROMPT, build_investigation_prompt
from app.mcp_server.logging_config import get_logger, log_with_fields
from app.mcp_server.security import AuthorizationError

logger = get_logger(__name__)

# Fails fast rather than hanging the whole investigation on one stalled
# dependency; bounded retries with backoff+jitter are botocore's default
# under "adaptive" mode.
_MODEL_BOTO_CONFIG = Config(retries={"max_attempts": 3, "mode": "adaptive"}, connect_timeout=5, read_timeout=30)


def _build_model(config: AgentConfiguration) -> BedrockModel:
    kwargs: dict[str, Any] = {
        "model_id": config.foundation_model_id,
        "region_name": config.aws_region,
        "max_tokens": config.max_output_tokens,
        "boto_client_config": _MODEL_BOTO_CONFIG,
    }
    if config.guardrail_id and config.guardrail_version:
        kwargs["guardrail_id"] = config.guardrail_id
        kwargs["guardrail_version"] = config.guardrail_version
        kwargs["guardrail_trace"] = "enabled"
    return BedrockModel(**kwargs)


def _build_mcp_client(config: AgentConfiguration, bearer_token: str) -> MCPClient:
    return MCPClient(
        url=config.gateway_url,
        headers={"Authorization": f"Bearer {bearer_token}"},
        startup_timeout=15,
    )


def invoke_agent(
    *,
    bearer_token: str,
    incident_description: str,
    service: str,
    environment: str,
    severity: str,
    correlation_id: str | None = None,
    config: AgentConfiguration | None = None,
) -> IncidentInvestigationResult:
    """Run one bounded investigation. Raises AuthorizationError (never
    retried - see reliability rules) if the bearer token itself is
    invalid; an authorization *denial* for the requested action is instead
    reported inside the returned result via refused/refusal_reason, since
    that is a legitimate, gracefully-handled outcome, not a fault."""
    config = config or get_agent_configuration()
    metrics: InvocationMetrics = start_invocation(correlation_id)

    user: AuthenticatedUser | None = None
    if config.cognito_discovery_url and config.cognito_issuer and config.cognito_client_id:
        user = validate_jwt(
            bearer_token,
            # Cognito's JWKS endpoint follows a fixed convention from the
            # issuer - config.cognito_discovery_url is the OIDC *discovery
            # document* URL (.../openid-configuration), a different
            # resource that PyJWKClient can't consume directly (confirmed
            # live: passing it produced "The JWK Set did not contain any
            # keys").
            jwks_uri=f"{config.cognito_issuer}/.well-known/jwks.json",
            issuer=config.cognito_issuer,
            client_id=config.cognito_client_id,
        )
        log_with_fields(
            logger,
            20,
            "caller_authenticated",
            user_id=user.user_id,
            correlation_id=metrics.correlation_id,
        )
    user_id = user.user_id if user else ""

    trace_sampled = should_sample_trace(config.trace_sampling_percentage)
    limiter = ToolCallLimiter(config.maximum_tool_calls)

    try:
        with _build_mcp_client(config, bearer_token) as mcp_client:
            tools = mcp_client.list_tools_sync()
            agent = Agent(
                model=_build_model(config),
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
                hooks=[limiter],
                trace_attributes={
                    "correlation_id": metrics.correlation_id,
                    "sampled": trace_sampled,
                },
            )

            prompt = build_investigation_prompt(
                user_id=user_id,
                correlation_id=metrics.correlation_id,
                incident_description=incident_description,
                service=service,
                environment=environment,
                severity=severity,
            )

            result = agent(
                prompt,
                structured_output_model=IncidentInvestigationResult,
                limits=Limits(
                    turns=config.maximum_agent_steps,
                    output_tokens=config.max_output_tokens,
                ),
            )
    except Exception as exc:
        metrics.mcp_failure_count += 1
        log_with_fields(
            logger,
            40,
            "agent_invocation_failed",
            error=str(exc),
            correlation_id=metrics.correlation_id,
        )
        finish_invocation(metrics)
        raise

    metrics.tool_call_count = limiter.tool_call_count
    metrics.stop_reason = result.stop_reason
    if result.metrics is not None:
        metrics.total_tokens = getattr(result.metrics, "total_tokens", None)
        metrics.output_tokens = getattr(result.metrics, "output_tokens", None)

    structured = result.structured_output
    if structured is None:
        structured = IncidentInvestigationResult(
            simulated_evidence_used=False,
            refused=True,
            refusal_reason="The model did not produce a structured result within the configured limits.",
        )

    metrics.refused = structured.refused
    metrics.retrieved_source_count = len(structured.citations)
    finish_invocation(metrics)

    return structured


app = BedrockAgentCoreApp()


@app.entrypoint
def handler(payload: dict[str, Any], context: RequestContext | None = None) -> dict[str, Any]:
    """AgentCore Runtime entrypoint.

    AgentCore Runtime's own custom_jwt_authorizer (terraform/agentcore.tf)
    validates the Authorization header before this handler ever runs, then
    *consumes* it - the platform does not forward it, or any other custom
    header, into context.request_headers for a direct client invocation
    (confirmed against a live deployment - only a couple of
    platform-internal headers survive). The HTTP request body is not
    filtered, so app/client/demo_client.py additionally includes the same
    bearer token as a payload field; this handler independently re-validates
    it (defense in depth, unforgeable since it's a signed JWT) and extracts
    the caller's identity from the verified claims, then forwards the same
    token on to the Gateway so each MCP tool call is authorized as the
    original caller, not as the runtime's own service identity.
    """
    bearer_token = payload.get("bearer_token", "")

    try:
        result = invoke_agent(
            bearer_token=bearer_token,
            incident_description=payload.get("incident_description", ""),
            service=payload.get("service", ""),
            environment=payload.get("environment", ""),
            severity=payload.get("severity", "SEV3"),
            correlation_id=(context.session_id if context else None) or payload.get("correlation_id"),
        )
    except AuthorizationError as exc:
        return {"refused": True, "refusal_reason": str(exc)}

    return result.model_dump()


if __name__ == "__main__":
    # Container entrypoint: starts the AgentCore Runtime HTTP server
    # (port 8080, /invocations and /ping) - see app/Dockerfile.
    app.run()
