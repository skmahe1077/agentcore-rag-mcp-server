"""get_resource_status: simulated by default; resource_type is restricted
to an explicit allow-list (enforced again here, beyond schema validation,
since this is the boundary that ultimately talks to AWS). Live lookups
return only the fields needed for investigation, never a raw API dump."""

from __future__ import annotations

from typing import Any

from app.mcp_server.clients import (
    autoscaling_client,
    ec2_client,
    elbv2_client,
    from_dynamodb_safe,
    get_table,
    lambda_client,
    rds_client,
)
from app.mcp_server.config import get_settings
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import GetResourceStatusInput, GetResourceStatusOutput
from app.mcp_server.security import (
    ALLOWED_RESOURCE_TYPES,
    ValidationError,
    enforce_identity_binding,
)

logger = get_logger(__name__)

# Fields surfaced to the model per resource type - deliberately narrow.
_SIMULATED_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "application_load_balancer": ("http_5xx_count", "http_4xx_count", "request_count"),
    "target_group": ("healthy_targets", "unhealthy_targets", "target_count"),
    "rds_database": (
        "database_connections",
        "max_connections",
        "replica_lag_seconds",
        "dependency_status",
    ),
    "auto_scaling_group": (
        "desired_capacity",
        "min_size",
        "max_size",
        "in_service_instances",
    ),
    "ec2_instance": ("cpu_utilization_percent", "status_check"),
    "lambda_function": ("error_count", "throttle_count", "concurrent_executions"),
}


def _simulated_lookup(resource_type: str, resource_identifier: str) -> dict[str, Any] | None:
    table = get_table()
    response = table.scan(
        FilterExpression="entity_type = :t AND resource_type = :rt AND resource_identifier = :id",
        ExpressionAttributeValues={
            ":t": "resource_status",
            ":rt": resource_type,
            ":id": resource_identifier,
        },
        Limit=50,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def _live_lookup(resource_type: str, resource_identifier: str, region: str) -> dict[str, Any] | None:
    if resource_type == "application_load_balancer":
        client = elbv2_client(region)
        lbs = client.describe_load_balancers(Names=[resource_identifier]).get("LoadBalancers", [])
        if not lbs:
            return None
        lb = lbs[0]
        return {"state": lb.get("State", {}).get("Code", "unknown"), "fields": {}}

    if resource_type == "target_group":
        client = elbv2_client(region)
        tgs = client.describe_target_groups(Names=[resource_identifier]).get("TargetGroups", [])
        if not tgs:
            return None
        health = client.describe_target_health(TargetGroupArn=tgs[0]["TargetGroupArn"]).get("TargetHealthDescriptions", [])
        healthy = sum(1 for h in health if h.get("TargetHealth", {}).get("State") == "healthy")
        return {
            "state": "active",
            "fields": {
                "healthy_targets": healthy,
                "unhealthy_targets": len(health) - healthy,
                "target_count": len(health),
            },
        }

    if resource_type == "ec2_instance":
        client = ec2_client(region)
        reservations = client.describe_instances(InstanceIds=[resource_identifier]).get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            return None
        instance = reservations[0]["Instances"][0]
        return {"state": instance.get("State", {}).get("Name", "unknown"), "fields": {}}

    if resource_type == "auto_scaling_group":
        client = autoscaling_client(region)
        groups = client.describe_auto_scaling_groups(AutoScalingGroupNames=[resource_identifier]).get("AutoScalingGroups", [])
        if not groups:
            return None
        group = groups[0]
        return {
            "state": "in_service",
            "fields": {
                "desired_capacity": group.get("DesiredCapacity", 0),
                "min_size": group.get("MinSize", 0),
                "max_size": group.get("MaxSize", 0),
                "in_service_instances": len(group.get("Instances", [])),
            },
        }

    if resource_type == "lambda_function":
        client = lambda_client(region)
        function = client.get_function(FunctionName=resource_identifier).get("Configuration", {})
        if not function:
            return None
        return {"state": function.get("State", "unknown"), "fields": {}}

    if resource_type == "rds_database":
        client = rds_client(region)
        instances = client.describe_db_instances(DBInstanceIdentifier=resource_identifier).get("DBInstances", [])
        if not instances:
            return None
        instance = instances[0]
        return {"state": instance.get("DBInstanceStatus", "unknown"), "fields": {}}

    return None


def get_resource_status(payload: GetResourceStatusInput) -> GetResourceStatusOutput:
    resource_type = payload.resource_type.value
    if resource_type not in ALLOWED_RESOURCE_TYPES:
        raise ValidationError("resource_type is not in the allow-list.")

    settings = get_settings()
    use_live = settings.enable_live_aws_diagnostics and not settings.use_simulated_operational_data

    if use_live:
        found = _live_lookup(resource_type, payload.resource_identifier, payload.region)
        simulated = False
        state = found.get("state", "unknown") if found else "unknown"
        fields = found.get("fields", {}) if found else {}
    else:
        item = _simulated_lookup(resource_type, payload.resource_identifier)
        simulated = True
        state = item.get("state", "unknown") if item else "unknown"
        keys = _SIMULATED_FIELD_KEYS.get(resource_type, ())
        fields = {k: from_dynamodb_safe(item[k]) for k in keys if item and k in item} if item else {}
        found = item

    log_with_fields(
        logger,
        20,
        "resource_status_returned",
        resource_type=resource_type,
        resource_identifier=payload.resource_identifier,
        found=found is not None,
        simulated=simulated,
    )

    return GetResourceStatusOutput(
        resource_type=resource_type,
        resource_identifier=payload.resource_identifier,
        state=state,
        fields=fields,
        simulated=simulated,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = GetResourceStatusInput.model_validate(event.get("arguments", event))
    set_correlation_id(payload.correlation_id)
    enforce_identity_binding(event, payload.user_id)
    return get_resource_status(payload).model_dump()
