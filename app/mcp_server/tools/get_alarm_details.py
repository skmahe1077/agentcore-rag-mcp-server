"""get_alarm_details: simulated by default; an optional read-only CloudWatch
lookup when enable_live_aws_diagnostics is true. The output schema is
identical either way so the agent and its prompts never need to change."""

from __future__ import annotations

from typing import Any

from app.mcp_server.clients import cloudwatch_client, get_table
from app.mcp_server.config import get_settings
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import GetAlarmDetailsInput, GetAlarmDetailsOutput
from app.mcp_server.security import enforce_identity_binding

logger = get_logger(__name__)


def _simulated_lookup(alarm_name: str) -> dict[str, Any] | None:
    table = get_table()
    # Small demo dataset: a bounded scan filtered to alarm items is
    # acceptable here. At production scale, add a GSI keyed by alarm_name.
    response = table.scan(
        FilterExpression="entity_type = :t AND alarm_name = :n",
        ExpressionAttributeValues={":t": "alarm", ":n": alarm_name},
        Limit=50,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def _live_lookup(alarm_name: str, region: str) -> dict[str, Any] | None:
    client = cloudwatch_client(region)
    response = client.describe_alarms(AlarmNames=[alarm_name])
    alarms = response.get("MetricAlarms", [])
    if not alarms:
        return None
    alarm = alarms[0]
    return {
        "alarm_state": alarm.get("StateValue", "UNKNOWN"),
        "metric": alarm.get("MetricName", ""),
        "threshold": alarm.get("Threshold", 0.0),
        "evaluation_period": alarm.get("Period", 0),
        "state_reason": alarm.get("StateReason", ""),
        "transition_time": str(alarm.get("StateUpdatedTimestamp", "")),
        "dimensions": {d["Name"]: d["Value"] for d in alarm.get("Dimensions", [])},
    }


def get_alarm_details(payload: GetAlarmDetailsInput) -> GetAlarmDetailsOutput:
    settings = get_settings()
    use_live = settings.enable_live_aws_diagnostics and not settings.use_simulated_operational_data

    if use_live:
        found = _live_lookup(payload.alarm_name, payload.region)
        simulated = False
    else:
        found = _simulated_lookup(payload.alarm_name)
        simulated = True

    if found is None:
        log_with_fields(
            logger,
            30,
            "alarm_not_found",
            alarm_name=payload.alarm_name,
            simulated=simulated,
        )
        return GetAlarmDetailsOutput(
            alarm_state="UNKNOWN",
            metric="",
            threshold=0.0,
            evaluation_period=0,
            state_reason="No alarm data found for the requested alarm_name.",
            transition_time="",
            dimensions={},
            simulated=simulated,
        )

    log_with_fields(
        logger,
        20,
        "alarm_details_returned",
        alarm_name=payload.alarm_name,
        simulated=simulated,
    )
    return GetAlarmDetailsOutput(
        alarm_state=found.get("alarm_state", "UNKNOWN"),
        metric=found.get("metric", ""),
        threshold=float(found.get("threshold", 0.0)),
        evaluation_period=int(found.get("evaluation_period", 0)),
        state_reason=found.get("state_reason", ""),
        transition_time=str(found.get("transition_time", "")),
        dimensions=dict(found.get("dimensions", {})),
        simulated=simulated,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = GetAlarmDetailsInput.model_validate(event.get("arguments", event))
    set_correlation_id(payload.correlation_id)
    enforce_identity_binding(event, payload.user_id)
    return get_alarm_details(payload).model_dump()
