"""get_recent_events: a bounded list of approved operational events.

Deliberately does not expose an unrestricted CloudWatch Logs Insights query
- the live path (when enabled) uses CloudTrail LookupEvents, which is
read-only and naturally bounded, rather than an arbitrary log search."""

from __future__ import annotations

from typing import Any

from app.mcp_server.clients import cloudtrail_client, get_table
from app.mcp_server.config import get_settings
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import (
    GetRecentEventsInput,
    GetRecentEventsOutput,
    OperationalEvent,
)
from app.mcp_server.security import enforce_identity_binding

logger = get_logger(__name__)

MAX_EVENTS = 20


def _simulated_lookup(service: str, environment: str, start_time: str, end_time: str) -> list[dict[str, Any]]:
    table = get_table()
    response = table.query(
        IndexName="gsi1",
        KeyConditionExpression="gsi1pk = :pk AND begins_with(gsi1sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": f"EVIDENCE#{service}#{environment}",
            ":prefix": "EVENT#",
        },
        Limit=MAX_EVENTS,
    )
    items = response.get("Items", [])
    return [i for i in items if start_time <= i.get("timestamp", "") <= end_time] or items[:MAX_EVENTS]


def _live_lookup(region: str, start_time: str, end_time: str) -> list[dict[str, Any]]:
    import datetime

    client = cloudtrail_client(region)
    response = client.lookup_events(
        StartTime=datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00")),
        EndTime=datetime.datetime.fromisoformat(end_time.replace("Z", "+00:00")),
        MaxResults=MAX_EVENTS,
    )
    events = []
    for event in response.get("Events", [])[:MAX_EVENTS]:
        events.append(
            {
                "event_type": event.get("EventName", "unknown"),
                "description": f"{event.get('EventName', 'unknown')} by {event.get('Username', 'unknown')}",
                "timestamp": str(event.get("EventTime", "")),
                "source": "cloudtrail",
            }
        )
    return events


def get_recent_events(payload: GetRecentEventsInput) -> GetRecentEventsOutput:
    settings = get_settings()
    use_live = settings.enable_live_aws_diagnostics and not settings.use_simulated_operational_data

    if use_live:
        raw_events = _live_lookup("eu-west-1", payload.start_time, payload.end_time)
        simulated = False
    else:
        raw_events = _simulated_lookup(
            payload.service,
            payload.environment.value,
            payload.start_time,
            payload.end_time,
        )
        simulated = True

    events = [
        OperationalEvent(
            event_type=e.get("event_type", "unknown"),
            description=e.get("description", ""),
            timestamp=str(e.get("timestamp", "")),
            source=e.get("source", "unknown"),
            simulated=simulated,
        )
        for e in raw_events[:MAX_EVENTS]
    ]

    log_with_fields(
        logger,
        20,
        "recent_events_returned",
        service=payload.service,
        environment=payload.environment.value,
        event_count=len(events),
        simulated=simulated,
    )

    return GetRecentEventsOutput(events=events, simulated=simulated)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = GetRecentEventsInput.model_validate(event.get("arguments", event))
    set_correlation_id(payload.correlation_id)
    enforce_identity_binding(event, payload.user_id)
    return get_recent_events(payload).model_dump()
