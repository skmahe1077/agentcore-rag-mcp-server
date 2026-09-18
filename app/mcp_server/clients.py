"""Cached boto3 client/resource factories.

Module-level caching gives connection reuse across warm Lambda invocations
(and across tool calls within one MCP server process) instead of building a
new client - and a new TCP/TLS connection pool - on every call.
"""

from __future__ import annotations

from decimal import Decimal
from functools import cache
from typing import Any

from botocore.config import Config

from app.mcp_server.config import get_settings


def to_dynamodb_safe(value: Any) -> Any:
    """Recursively convert float -> Decimal (DynamoDB's boto3 resource API
    rejects native float) so callers can build items with ordinary
    JSON-shaped Python values."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamodb_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamodb_safe(v) for v in value]
    return value


def from_dynamodb_safe(value: Any) -> Any:
    """Recursively convert Decimal -> int/float so items read back from
    DynamoDB are ordinary JSON-serializable Python values."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamodb_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [from_dynamodb_safe(v) for v in value]
    return value


# Bounded retries with exponential backoff+jitter; short connect/read
# timeouts so a stalled dependency fails fast instead of exhausting the
# agent's overall tool-call budget.
_BOTO_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "adaptive"},
    connect_timeout=3,
    read_timeout=6,
)


@cache
def dynamodb_resource(region: str | None = None) -> Any:
    import boto3

    return boto3.resource("dynamodb", region_name=region or get_settings().aws_region, config=_BOTO_CONFIG)


def get_table(region: str | None = None) -> Any:
    settings = get_settings()
    if not settings.table_name:
        raise RuntimeError("TABLE_NAME is not configured.")
    return dynamodb_resource(region).Table(settings.table_name)


@cache
def bedrock_agent_runtime_client(region: str | None = None) -> Any:
    import boto3

    return boto3.client(
        "bedrock-agent-runtime",
        region_name=region or get_settings().aws_region,
        config=_BOTO_CONFIG,
    )


@cache
def cloudwatch_client(region: str) -> Any:
    import boto3

    return boto3.client("cloudwatch", region_name=region, config=_BOTO_CONFIG)


@cache
def elbv2_client(region: str) -> Any:
    import boto3

    return boto3.client("elbv2", region_name=region, config=_BOTO_CONFIG)


@cache
def ec2_client(region: str) -> Any:
    import boto3

    return boto3.client("ec2", region_name=region, config=_BOTO_CONFIG)


@cache
def autoscaling_client(region: str) -> Any:
    import boto3

    return boto3.client("autoscaling", region_name=region, config=_BOTO_CONFIG)


@cache
def lambda_client(region: str) -> Any:
    import boto3

    return boto3.client("lambda", region_name=region, config=_BOTO_CONFIG)


@cache
def rds_client(region: str) -> Any:
    import boto3

    return boto3.client("rds", region_name=region, config=_BOTO_CONFIG)


@cache
def cloudtrail_client(region: str) -> Any:
    import boto3

    return boto3.client("cloudtrail", region_name=region, config=_BOTO_CONFIG)
