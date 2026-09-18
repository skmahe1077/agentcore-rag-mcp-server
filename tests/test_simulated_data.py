"""Every piece of demo operational evidence is explicitly marked simulated
(#18), at the data layer and at each tool's output layer."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIMULATED_DATA_DIR = REPO_ROOT / "sample-data" / "simulated-operations"


def test_all_alarms_are_marked_simulated():
    alarms = json.loads((SIMULATED_DATA_DIR / "alarms.json").read_text())
    assert alarms
    assert all(alarm["simulated"] is True for alarm in alarms)


def test_all_resource_statuses_are_marked_simulated():
    resources = json.loads((SIMULATED_DATA_DIR / "resource_status.json").read_text())
    assert resources
    assert all(resource["simulated"] is True for resource in resources)


def test_all_recent_events_are_marked_simulated():
    events = json.loads((SIMULATED_DATA_DIR / "recent_events.json").read_text())
    assert events
    assert all(event["simulated"] is True for event in events)


def test_get_alarm_details_output_reports_simulated_flag(dynamodb_table):
    from app.mcp_server.schemas import GetAlarmDetailsInput
    from app.mcp_server.tools.get_alarm_details import get_alarm_details

    result = get_alarm_details(
        GetAlarmDetailsInput(
            alarm_name="checkout-http-5xx-high",
            region="eu-west-1",
            user_id="demo-incident-commander",
        )
    )
    assert result.simulated is True


def test_get_resource_status_output_reports_simulated_flag(dynamodb_table):
    from app.mcp_server.schemas import GetResourceStatusInput
    from app.mcp_server.tools.get_resource_status import get_resource_status

    result = get_resource_status(
        GetResourceStatusInput(
            resource_type="rds_database",
            resource_identifier="checkout-db-prod",
            region="eu-west-1",
            user_id="demo-incident-commander",
        )
    )
    assert result.simulated is True


def test_get_recent_events_output_reports_simulated_flag(dynamodb_table):
    from app.mcp_server.schemas import GetRecentEventsInput
    from app.mcp_server.tools.get_recent_events import get_recent_events

    result = get_recent_events(
        GetRecentEventsInput(
            service="checkout",
            environment="production",
            start_time="2026-09-18T00:00:00Z",
            end_time="2026-09-18T23:59:59Z",
            user_id="demo-incident-commander",
        )
    )
    assert result.simulated is True
    assert all(event.simulated is True for event in result.events)
