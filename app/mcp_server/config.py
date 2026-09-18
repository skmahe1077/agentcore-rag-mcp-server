"""Environment-driven configuration for the MCP server and its tools.

Every setting is read from an environment variable so the same code runs
unchanged locally, in a Lambda tool execution, and inside the AgentCore
Runtime - only the environment differs between them.
"""

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
class Settings:
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "eu-west-1"))
    table_name: str = field(default_factory=lambda: os.environ.get("TABLE_NAME", ""))
    knowledge_base_id: str = field(default_factory=lambda: os.environ.get("KNOWLEDGE_BASE_ID", ""))

    use_simulated_operational_data: bool = field(default_factory=lambda: _bool_env("USE_SIMULATED_OPERATIONAL_DATA", True))
    enable_live_aws_diagnostics: bool = field(default_factory=lambda: _bool_env("ENABLE_LIVE_AWS_DIAGNOSTICS", False))

    retrieval_results: int = field(default_factory=lambda: _int_env("RETRIEVAL_RESULTS", 4))
    max_retrieval_results_cap: int = field(default_factory=lambda: _int_env("MAX_RETRIEVAL_RESULTS_CAP", 10))

    enable_debug_logging: bool = field(default_factory=lambda: _bool_env("ENABLE_DEBUG_LOGGING", False))
    enable_detailed_metrics: bool = field(default_factory=lambda: _bool_env("ENABLE_DETAILED_METRICS", False))

    tool_timeout_seconds: float = field(default_factory=lambda: float(os.environ.get("TOOL_TIMEOUT_SECONDS", "8")))


def get_settings() -> Settings:
    """Return a fresh Settings snapshot. Not cached, so tests can mutate
    os.environ between calls without needing a reset hook."""
    return Settings()
