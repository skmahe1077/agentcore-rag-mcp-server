"""search_runbooks retrieval-filtering tests, with the Bedrock
bedrock-agent-runtime Retrieve API mocked (no live AWS call). Covers:
  - authorized retrieval returns the correct runbook (#1)
  - a read-only operator cannot retrieve restricted content, even if the
    upstream filter somehow let it through (#2, defense in depth)
  - filtering by service and environment (#3)
  - superseded runbooks are excluded (#4)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.mcp_server.schemas import SearchRunbooksInput
from app.mcp_server.tools.search_runbooks import search_runbooks

_ALB_RUNBOOK = {
    "content": {"text": "Retrieve the triggering alarm and note alarm_state..."},
    "location": {"s3Location": {"uri": "s3://bucket/runbooks/alb-http-5xx-investigation.md"}},
    "score": 0.91,
    "metadata": {
        "document_id": "RB-ALB-5XX-001",
        "title": "ALB / Target Group HTTP 5xx Investigation",
        "version": 3,
        "classification": "internal",
        "status": "active",
        "service": "checkout",
        "environment": "production",
    },
}

_SUPERSEDED_RUNBOOK = {
    "content": {"text": "Superseded - do not use."},
    "location": {"s3Location": {"uri": "s3://bucket/runbooks/alb-http-5xx-investigation-v2-superseded.md"}},
    "score": 0.4,
    "metadata": {
        "document_id": "RB-ALB-5XX-001",
        "title": "ALB / Target Group HTTP 5xx Investigation (superseded)",
        "version": 2,
        "classification": "internal",
        "status": "superseded",
        "service": "checkout",
        "environment": "production",
    },
}

_RESTRICTED_RUNBOOK = {
    "content": {"text": "Forced target-group deregistration procedure..."},
    "location": {"s3Location": {"uri": "s3://bucket/restricted/production-recovery-commands.md"}},
    "score": 0.85,
    "metadata": {
        "document_id": "RS-RECOVERY-001",
        "title": "Production Recovery Commands",
        "version": 2,
        "classification": "restricted",
        "status": "active",
        "service": "checkout",
        "environment": "production",
    },
}


def _mock_retrieve_client(results):
    client = MagicMock()
    client.retrieve.return_value = {"retrievalResults": results}
    return client


def _search_input(user_id: str) -> SearchRunbooksInput:
    return SearchRunbooksInput(
        query="checkout 5xx investigation",
        service="checkout",
        environment="production",
        severity="SEV2",
        max_results=4,
        user_id=user_id,
    )


@patch("app.mcp_server.tools.search_runbooks.bedrock_agent_runtime_client")
def test_authorized_engineer_retrieves_correct_runbook(mock_client_factory, dynamodb_table):
    mock_client_factory.return_value = _mock_retrieve_client([_ALB_RUNBOOK, _SUPERSEDED_RUNBOOK])

    result = search_runbooks(_search_input("demo-incident-commander"))

    ids = [p.document_id for p in result.retrieved_passages]
    assert "RB-ALB-5XX-001" in ids
    assert any(p.version == 3 for p in result.retrieved_passages)
    assert len(result.citations) >= 1


@patch("app.mcp_server.tools.search_runbooks.bedrock_agent_runtime_client")
def test_superseded_runbook_is_excluded(mock_client_factory, dynamodb_table):
    mock_client_factory.return_value = _mock_retrieve_client([_ALB_RUNBOOK, _SUPERSEDED_RUNBOOK])

    result = search_runbooks(_search_input("demo-incident-commander"))

    versions = [p.version for p in result.retrieved_passages if p.document_id == "RB-ALB-5XX-001"]
    assert 2 not in versions
    assert 3 in versions


@patch("app.mcp_server.tools.search_runbooks.bedrock_agent_runtime_client")
def test_read_only_operator_cannot_retrieve_restricted_content(mock_client_factory, dynamodb_table):
    # Even though the upstream call "returns" a restricted document (as if
    # the Bedrock-side filter had a bug), the tool must still withhold it
    # for an unauthorized role - defense in depth.
    mock_client_factory.return_value = _mock_retrieve_client([_ALB_RUNBOOK, _RESTRICTED_RUNBOOK])

    result = search_runbooks(_search_input("demo-read-only-operator"))

    ids = [p.document_id for p in result.retrieved_passages]
    assert "RS-RECOVERY-001" not in ids
    assert "RB-ALB-5XX-001" in ids


@patch("app.mcp_server.tools.search_runbooks.bedrock_agent_runtime_client")
def test_incident_commander_can_retrieve_restricted_content(mock_client_factory, dynamodb_table):
    mock_client_factory.return_value = _mock_retrieve_client([_ALB_RUNBOOK, _RESTRICTED_RUNBOOK])

    result = search_runbooks(_search_input("demo-incident-commander"))

    ids = [p.document_id for p in result.retrieved_passages]
    assert "RS-RECOVERY-001" in ids


@patch("app.mcp_server.tools.search_runbooks.bedrock_agent_runtime_client")
def test_query_filters_by_service_and_environment(mock_client_factory, dynamodb_table):
    mock_client = _mock_retrieve_client([_ALB_RUNBOOK])
    mock_client_factory.return_value = mock_client

    search_runbooks(_search_input("demo-incident-commander"))

    call_kwargs = mock_client.retrieve.call_args.kwargs
    filter_clauses = call_kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]["andAll"]
    equals_clauses = {c["equals"]["key"]: c["equals"]["value"] for c in filter_clauses if "equals" in c}
    assert equals_clauses["service"] == "checkout"
    assert equals_clauses["environment"] == "production"
    assert equals_clauses["status"] == "active"


def test_unknown_user_gets_no_retrieval(dynamodb_table):
    result = search_runbooks(_search_input("nobody"))
    assert result.retrieved_passages == []
    assert "Denied" in result.authorization_decision
