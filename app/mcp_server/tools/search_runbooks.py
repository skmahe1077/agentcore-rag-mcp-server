"""search_runbooks: authorized, metadata-filtered retrieval from the Bedrock
Knowledge Base.

Authorization is enforced here in application code, not left to the model:
the caller's permitted classifications are re-derived from DynamoDB
(security.resolve_entitlement) and built into the Bedrock retrieval filter
*before* any content is fetched, then re-checked on every returned result as
defense in depth. An unauthorized caller never receives restricted content,
and the tool never asks the model to decide what it's allowed to see.
"""

from __future__ import annotations

from typing import Any

from app.mcp_server.clients import bedrock_agent_runtime_client, get_table
from app.mcp_server.config import get_settings
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import (
    RetrievedPassage,
    SearchRunbooksInput,
    SearchRunbooksOutput,
)
from app.mcp_server.security import enforce_identity_binding, resolve_entitlement

logger = get_logger(__name__)


def _build_filter(environment: str, service: str, permitted_classifications: list[str]) -> dict[str, Any]:
    # "equals" against a STRING_LIST metadata attribute matches when the
    # list contains the value (service/environment are stored as lists to
    # allow a document to apply to more than one). "in" against
    # classification (a single STRING per document) matches any permitted
    # value. Verify this contract against the live Bedrock Retrieve API
    # before first use - see README.md manual-verification steps.
    return {
        "andAll": [
            {"equals": {"key": "status", "value": "active"}},
            {"equals": {"key": "environment", "value": environment}},
            {"equals": {"key": "service", "value": service}},
            {"in": {"key": "classification", "value": permitted_classifications}},
        ]
    }


def search_runbooks(payload: SearchRunbooksInput) -> SearchRunbooksOutput:
    settings = get_settings()
    entitlement = resolve_entitlement(payload.user_id, get_table())

    if not entitlement.found or not entitlement.permitted_classifications:
        log_with_fields(
            logger,
            30,
            "search_runbooks_denied",
            user_id=payload.user_id,
            reason="no_entitlement",
        )
        return SearchRunbooksOutput(
            retrieved_passages=[],
            relevance_scores=[],
            document_metadata=[],
            citations=[],
            version_information=[],
            authorization_decision="Denied: no entitlement found for user - no retrieval performed.",
        )

    max_results = min(
        payload.max_results,
        settings.max_retrieval_results_cap,
        settings.retrieval_results or payload.max_results,
    )

    client = bedrock_agent_runtime_client()
    response = client.retrieve(
        knowledgeBaseId=settings.knowledge_base_id,
        retrievalQuery={"text": payload.query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": max_results,
                "filter": _build_filter(
                    payload.environment.value,
                    payload.service,
                    list(entitlement.permitted_classifications),
                ),
            }
        },
    )

    passages: list[RetrievedPassage] = []
    citations: list[str] = []
    version_information: list[str] = []
    document_metadata: list[dict[str, Any]] = []

    for result in response.get("retrievalResults", []):
        metadata = result.get("metadata", {})
        classification = metadata.get("classification", "restricted")

        # Defense in depth: never surface a result whose classification the
        # filter should have already excluded, or that isn't active.
        if classification not in entitlement.permitted_classifications:
            continue
        if metadata.get("status", "active") != "active":
            continue

        document_id = metadata.get("document_id", "unknown")
        title = metadata.get("title", "Untitled")
        version = int(metadata.get("version", 0))
        source_uri = result.get("location", {}).get("s3Location", {}).get("uri", "")
        excerpt = result.get("content", {}).get("text", "")[:1000]
        score = float(result.get("score", 0.0))

        passages.append(
            RetrievedPassage(
                document_id=document_id,
                title=title,
                version=version,
                excerpt=excerpt,
                score=score,
                classification=classification,
                source_uri=source_uri,
            )
        )
        citations.append(f"{title} ({document_id}, v{version})")
        version_information.append(f"{document_id} v{version} (status: active)")
        document_metadata.append(metadata)

    log_with_fields(
        logger,
        20,
        "search_runbooks_completed",
        user_id=payload.user_id,
        role=entitlement.role,
        result_count=len(passages),
    )

    return SearchRunbooksOutput(
        retrieved_passages=passages,
        relevance_scores=[p.score for p in passages],
        document_metadata=document_metadata,
        citations=citations,
        version_information=version_information,
        authorization_decision=(f"Applied classification ceiling {list(entitlement.permitted_classifications)} for role '{entitlement.role}'."),
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = SearchRunbooksInput.model_validate(event.get("arguments", event))
    set_correlation_id(payload.correlation_id)
    enforce_identity_binding(event, payload.user_id)
    return search_runbooks(payload).model_dump()
