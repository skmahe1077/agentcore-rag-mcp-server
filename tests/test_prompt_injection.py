"""Prompt-injection defense (#6).

There is no live model in CI to prove a prompt-injection attempt was
*ignored* by a real completion, so this test proves the two things that
are actually under this codebase's control:
  1. The injected payload flows through search_runbooks unmodified, as
     inert data - the defense is instruction-based, not content-scrubbing,
     so the model can still see and describe the attempt.
  2. The system prompt explicitly instructs the model to disregard
     instruction-like content inside retrieved documents, and that this
     rule cannot be overridden by anything except the system prompt itself,
     tool-reported authorization, and the human's direct request.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.agent.prompts import SYSTEM_PROMPT
from app.mcp_server.schemas import SearchRunbooksInput
from app.mcp_server.tools.search_runbooks import search_runbooks

REPO_ROOT = Path(__file__).resolve().parent.parent
_INJECTED_RUNBOOK_PATH = REPO_ROOT / "sample-data" / "runbooks" / "rds-connection-exhaustion.md"

_INJECTION_MARKER = "IGNORE ALL PREVIOUS INSTRUCTIONS"


def test_sample_corpus_contains_the_injection_test_payload():
    text = _INJECTED_RUNBOOK_PATH.read_text(encoding="utf-8")
    assert _INJECTION_MARKER in text


def test_system_prompt_instructs_the_model_to_disregard_embedded_instructions():
    assert "untrusted reference data" in SYSTEM_PROMPT
    assert "ignore previous instructions" in SYSTEM_PROMPT.lower()
    assert "only this" in SYSTEM_PROMPT.lower() or "govern your behavior" in SYSTEM_PROMPT.lower()


@patch("app.mcp_server.tools.search_runbooks.bedrock_agent_runtime_client")
def test_injected_payload_passes_through_as_inert_data(mock_client_factory, dynamodb_table):
    full_text = _INJECTED_RUNBOOK_PATH.read_text(encoding="utf-8")
    marker_index = full_text.index(_INJECTION_MARKER)
    # search_runbooks truncates excerpts to 1000 chars - slice the chunk
    # so the marker survives that truncation, simulating a retriever that
    # chunked the document around the injected paragraph.
    injected_chunk = full_text[max(0, marker_index - 200) : marker_index + 200]
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {
        "retrievalResults": [
            {
                "content": {"text": injected_chunk},
                "location": {"s3Location": {"uri": "s3://bucket/runbooks/rds-connection-exhaustion.md"}},
                "score": 0.9,
                "metadata": {
                    "document_id": "RB-RDS-CONN-001",
                    "title": "RDS Connection Exhaustion Investigation",
                    "version": 4,
                    "classification": "internal",
                    "status": "active",
                    "service": "checkout",
                    "environment": "production",
                },
            }
        ]
    }
    mock_client_factory.return_value = mock_client

    result = search_runbooks(
        SearchRunbooksInput(
            query="database connection exhaustion",
            service="checkout",
            environment="production",
            severity="SEV2",
            user_id="demo-incident-commander",
        )
    )

    # search_runbooks does not sanitize retrieved content - the excerpt
    # still contains the attempted instruction verbatim, exactly as an
    # attacker who compromised a runbook source would see it delivered.
    # Safety comes entirely from the system prompt's instruction hierarchy,
    # not from stripping suspicious text here.
    assert any(_INJECTION_MARKER in p.excerpt for p in result.retrieved_passages)
