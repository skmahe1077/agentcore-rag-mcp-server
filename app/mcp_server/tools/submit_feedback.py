"""submit_feedback: stores a bounded, redacted rating/comment - never the
full prompt or conversation."""

from __future__ import annotations

import time
from typing import Any

from app.mcp_server.clients import get_table
from app.mcp_server.logging_config import get_logger, log_with_fields, set_correlation_id
from app.mcp_server.schemas import SubmitFeedbackInput, SubmitFeedbackOutput
from app.mcp_server.security import redact_text

logger = get_logger(__name__)

FEEDBACK_TTL_SECONDS = 90 * 24 * 60 * 60


def submit_feedback(payload: SubmitFeedbackInput) -> SubmitFeedbackOutput:
    table = get_table()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    table.put_item(
        Item={
            "pk": f"FEEDBACK#{payload.session_id}",
            "sk": f"FEEDBACK#{now}",
            "entity_type": "feedback",
            "session_id": payload.session_id,
            "rating": payload.rating,
            "comments": redact_text(payload.comments)[:1000],
            "created_at": now,
            "ttl": int(time.time()) + FEEDBACK_TTL_SECONDS,
        }
    )

    log_with_fields(
        logger,
        20,
        "feedback_submitted",
        session_id=payload.session_id,
        rating=payload.rating,
    )
    return SubmitFeedbackOutput(status="recorded")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    payload = SubmitFeedbackInput.model_validate(event)
    set_correlation_id(payload.correlation_id)
    return submit_feedback(payload).model_dump()
