"""Local/development MCP server: assembles the same tool implementations
used by the production Lambda handlers into one stdio MCP server.

In the deployed architecture, AgentCore Gateway federates the 7 Lambda
functions (lambda-tools.tf) into one MCP endpoint for the agent - there is
no long-running MCP server process in production. This module exists so the
tools can be exercised locally (e.g. with an MCP inspector) and imported
directly by unit tests, using the exact same business-logic functions.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from app.mcp_server.schemas import (
    CheckOperatorPermissionsInput,
    CreateIncidentRecordInput,
    GetAlarmDetailsInput,
    GetRecentEventsInput,
    GetResourceStatusInput,
    SearchRunbooksInput,
    SubmitFeedbackInput,
)
from app.mcp_server.tools.check_operator_permissions import check_operator_permissions
from app.mcp_server.tools.create_incident_record import create_incident_record
from app.mcp_server.tools.get_alarm_details import get_alarm_details
from app.mcp_server.tools.get_recent_events import get_recent_events
from app.mcp_server.tools.get_resource_status import get_resource_status
from app.mcp_server.tools.search_runbooks import search_runbooks
from app.mcp_server.tools.submit_feedback import submit_feedback

server = MCPServer(
    name="cloud-operations-runbook-assistant",
    instructions=(
        "Tools for investigating AWS incidents using approved runbooks and operational evidence. "
        "Every tool re-verifies authorization independently; write actions require explicit confirmation."
    ),
)


@server.tool(name="check_operator_permissions")
def _check_operator_permissions(payload: CheckOperatorPermissionsInput) -> dict:
    return check_operator_permissions(payload).model_dump()


@server.tool(name="search_runbooks")
def _search_runbooks(payload: SearchRunbooksInput) -> dict:
    return search_runbooks(payload).model_dump()


@server.tool(name="get_alarm_details")
def _get_alarm_details(payload: GetAlarmDetailsInput) -> dict:
    return get_alarm_details(payload).model_dump()


@server.tool(name="get_resource_status")
def _get_resource_status(payload: GetResourceStatusInput) -> dict:
    return get_resource_status(payload).model_dump()


@server.tool(name="get_recent_events")
def _get_recent_events(payload: GetRecentEventsInput) -> dict:
    return get_recent_events(payload).model_dump()


@server.tool(name="create_incident_record")
def _create_incident_record(payload: CreateIncidentRecordInput) -> dict:
    return create_incident_record(payload).model_dump()


@server.tool(name="submit_feedback")
def _submit_feedback(payload: SubmitFeedbackInput) -> dict:
    return submit_feedback(payload).model_dump()


if __name__ == "__main__":
    server.run(transport="stdio")
