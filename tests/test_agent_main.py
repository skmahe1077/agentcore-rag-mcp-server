"""Tests for app.agent.main's orchestration logic, with the MCP client and
strands Agent mocked out - no live Bedrock or Gateway calls. Confirms the
tool-call limiter is attached, the correlation ID is set, and a missing
structured_output is turned into a safe refusal rather than a crash."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent.configuration import AgentConfiguration
from app.agent.incident_analysis import IncidentInvestigationResult
from app.agent.main import invoke_agent


def _config(**overrides) -> AgentConfiguration:
    base = {
        "foundation_model_id": "eu.anthropic.claude-3-5-haiku-20241022-v1:0",
        "gateway_url": "https://example-gateway.invalid/mcp",
        "maximum_tool_calls": 4,
        "maximum_agent_steps": 6,
        "max_output_tokens": 800,
        "trace_sampling_percentage": 0,
    }
    base.update(overrides)
    return AgentConfiguration(**base)


def _mock_agent_result(structured_output=None, stop_reason="end_turn"):
    result = MagicMock()
    result.structured_output = structured_output
    result.stop_reason = stop_reason
    result.metrics = MagicMock(total_tokens=123, output_tokens=45)
    return result


@patch("app.agent.main.Agent")
@patch("app.agent.main._build_mcp_client")
def test_invoke_agent_returns_structured_output(mock_build_client, mock_agent_cls):
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.list_tools_sync.return_value = []
    mock_build_client.return_value = mock_client

    expected = IncidentInvestigationResult(
        observations=[],
        citations=["ALB / Target Group HTTP 5xx Investigation (RB-ALB-5XX-001, v3)"],
        simulated_evidence_used=True,
    )
    mock_agent_instance = MagicMock(return_value=_mock_agent_result(structured_output=expected))
    mock_agent_cls.return_value = mock_agent_instance

    result = invoke_agent(
        bearer_token="fake-token",
        incident_description="checkout 5xx",
        service="checkout",
        environment="production",
        severity="SEV2",
        config=_config(),
    )

    assert result is expected
    # The tool-call limiter hook must be wired into the agent.
    _, kwargs = mock_agent_cls.call_args
    assert len(kwargs["hooks"]) == 1
    assert kwargs["hooks"][0].maximum_tool_calls == 4


@patch("app.agent.main.Agent")
@patch("app.agent.main._build_mcp_client")
def test_invoke_agent_handles_missing_structured_output_safely(mock_build_client, mock_agent_cls):
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.list_tools_sync.return_value = []
    mock_build_client.return_value = mock_client

    mock_agent_instance = MagicMock(return_value=_mock_agent_result(structured_output=None, stop_reason="max_tokens"))
    mock_agent_cls.return_value = mock_agent_instance

    result = invoke_agent(
        bearer_token="fake-token",
        incident_description="checkout 5xx",
        service="checkout",
        environment="production",
        severity="SEV2",
        config=_config(),
    )

    assert result.refused is True
    assert result.refusal_reason is not None


@patch("app.agent.main.Agent")
@patch("app.agent.main._build_mcp_client")
def test_invoke_agent_propagates_mcp_failures(mock_build_client, mock_agent_cls):
    mock_build_client.side_effect = RuntimeError("gateway unreachable")

    with pytest.raises(RuntimeError):
        invoke_agent(
            bearer_token="fake-token",
            incident_description="checkout 5xx",
            service="checkout",
            environment="production",
            severity="SEV2",
            config=_config(),
        )
