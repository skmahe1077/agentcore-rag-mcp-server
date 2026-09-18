"""Structured output shape for an investigation response.

Passed to strands.Agent as structured_output_model so the model's final
answer is forced into this schema - observations separated from
recommendations, citations required, simulated evidence flagged - rather
than free text the caller has to parse heuristically.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Observation(BaseModel):
    fact: str = Field(description="A single fact drawn directly from tool output.")
    source_tool: str = Field(description="The MCP tool that returned this fact, e.g. get_alarm_details.")


class IncidentInvestigationResult(BaseModel):
    observations: list[Observation] = Field(
        default_factory=list,
        description="Facts drawn directly from tool output, each with its source.",
    )
    possible_causes: list[str] = Field(
        default_factory=list,
        description="Possible causes supported by the observations. Never an unsupported assertion of root cause.",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Suggested next steps, clearly distinguished from observations.",
    )
    assumptions: list[str] = Field(default_factory=list, description="Any assumption made, labeled as such.")
    citations: list[str] = Field(
        default_factory=list,
        description="Runbook citations as 'Title (document_id, vN)'.",
    )
    simulated_evidence_used: bool = Field(description="True if any observation relied on simulated (non-live) evidence.")
    refused: bool = Field(
        default=False,
        description="True if the investigation was refused (e.g. unauthorized).",
    )
    refusal_reason: str | None = Field(default=None, description="Why the request was refused, if refused=true.")
