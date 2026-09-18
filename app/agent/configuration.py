"""Environment-driven configuration for the agent, mirroring
app/mcp_server/config.py's pattern so the same code runs unchanged in
AgentCore Runtime, a container, or a local shell."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class AgentConfiguration:
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "eu-west-1"))

    foundation_model_id: str = field(default_factory=lambda: os.environ.get("FOUNDATION_MODEL_ID", ""))
    max_output_tokens: int = field(default_factory=lambda: _int_env("MAX_OUTPUT_TOKENS", 1200))
    maximum_tool_calls: int = field(default_factory=lambda: _int_env("MAXIMUM_TOOL_CALLS", 8))
    maximum_agent_steps: int = field(default_factory=lambda: _int_env("MAXIMUM_AGENT_STEPS", 10))
    retrieval_results: int = field(default_factory=lambda: _int_env("RETRIEVAL_RESULTS", 4))

    gateway_url: str = field(default_factory=lambda: os.environ.get("GATEWAY_URL", ""))

    cognito_discovery_url: str = field(default_factory=lambda: os.environ.get("COGNITO_DISCOVERY_URL", ""))
    cognito_issuer: str = field(default_factory=lambda: os.environ.get("COGNITO_ISSUER", ""))
    cognito_client_id: str = field(default_factory=lambda: os.environ.get("COGNITO_CLIENT_ID", ""))

    trace_sampling_percentage: int = field(default_factory=lambda: _int_env("TRACE_SAMPLING_PERCENTAGE", 10))
    enable_debug_logging: bool = field(default_factory=lambda: _bool_env("ENABLE_DEBUG_LOGGING", False))

    # Optional Bedrock Guardrails - off by default (see variables.tf notes);
    # set both to attach a guardrail without any code change.
    guardrail_id: str = field(default_factory=lambda: os.environ.get("BEDROCK_GUARDRAIL_ID", ""))
    guardrail_version: str = field(default_factory=lambda: os.environ.get("BEDROCK_GUARDRAIL_VERSION", ""))


def get_agent_configuration() -> AgentConfiguration:
    return AgentConfiguration()
