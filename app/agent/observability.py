"""Agent-side observability: correlation IDs, sampled tracing, a hard cap
on MCP tool calls per invocation (independent of the model's own turn
limit), and structured invocation metrics logging."""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass
from typing import Any

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from app.mcp_server.logging_config import (
    get_logger,
    log_with_fields,
    set_correlation_id,
)

logger = get_logger(__name__)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def should_sample_trace(trace_sampling_percentage: int) -> bool:
    if trace_sampling_percentage >= 100:
        return True
    if trace_sampling_percentage <= 0:
        return False
    return random.random() * 100 < trace_sampling_percentage


class ToolCallLimiter(HookProvider):
    """Cancels tool calls once the per-invocation cap is reached, independent
    of and in addition to the model's own turn/step limit - the two limits
    protect against different failure modes (a chatty model vs. a model
    stuck retrying one tool)."""

    def __init__(self, maximum_tool_calls: int) -> None:
        self.maximum_tool_calls = maximum_tool_calls
        self.tool_call_count = 0

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)

    def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        self.tool_call_count += 1
        if self.tool_call_count > self.maximum_tool_calls:
            event.cancel_tool = (
                f"Tool-call limit reached ({self.maximum_tool_calls} per investigation) - reporting findings so far instead of continuing."
            )
            log_with_fields(
                logger,
                30,
                "tool_call_limit_reached",
                maximum_tool_calls=self.maximum_tool_calls,
            )


@dataclass
class InvocationMetrics:
    correlation_id: str
    started_at: float
    model_duration_seconds: float | None = None
    tool_call_count: int = 0
    retrieved_source_count: int = 0
    authorization_denied: bool = False
    refused: bool = False
    mcp_failure_count: int = 0
    total_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None


def start_invocation(correlation_id: str | None = None) -> InvocationMetrics:
    cid = correlation_id or new_correlation_id()
    set_correlation_id(cid)
    metrics = InvocationMetrics(correlation_id=cid, started_at=time.monotonic())
    log_with_fields(logger, 20, "agent_invocation_started", correlation_id=cid)
    return metrics


def finish_invocation(metrics: InvocationMetrics) -> None:
    duration = time.monotonic() - metrics.started_at
    log_with_fields(
        logger,
        20,
        "agent_invocation_completed",
        correlation_id=metrics.correlation_id,
        duration_seconds=round(duration, 3),
        tool_call_count=metrics.tool_call_count,
        retrieved_source_count=metrics.retrieved_source_count,
        authorization_denied=metrics.authorization_denied,
        refused=metrics.refused,
        mcp_failure_count=metrics.mcp_failure_count,
        total_tokens=metrics.total_tokens,
        output_tokens=metrics.output_tokens,
        stop_reason=metrics.stop_reason,
    )
