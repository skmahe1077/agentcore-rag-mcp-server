"""Observations and recommendations are structurally distinct fields
(#14) - the model cannot blend a recommendation into the observations list
without violating the schema, since they are separate typed fields rather
than one free-text block."""

from __future__ import annotations

from app.agent.incident_analysis import IncidentInvestigationResult, Observation


def test_observations_and_recommendations_are_separate_fields():
    result = IncidentInvestigationResult(
        observations=[
            Observation(
                fact="healthy_targets=1, unhealthy_targets=2",
                source_tool="get_resource_status",
            )
        ],
        possible_causes=["Recent deployment may have introduced a regression."],
        recommendations=["Consider rolling back the latest deployment per emergency-change-procedure.md."],
        assumptions=["Assuming no concurrent unrelated deployment occurred."],
        citations=["ALB / Target Group HTTP 5xx Investigation (RB-ALB-5XX-001, v3)"],
        simulated_evidence_used=True,
    )

    assert result.observations[0].fact != result.recommendations[0]
    fields = IncidentInvestigationResult.model_fields
    assert "observations" in fields
    assert "recommendations" in fields
    # Genuinely independent fields, not one shared free-text block.
    assert fields["observations"] is not fields["recommendations"]


def test_each_observation_carries_its_source_tool():
    # Every observation must be traceable to the tool call that produced
    # it - this is what "grounded" means operationally.
    obs = Observation(fact="alarm_state=ALARM", source_tool="get_alarm_details")
    assert obs.source_tool == "get_alarm_details"


def test_refusal_is_a_distinct_outcome_from_a_normal_result():
    refused = IncidentInvestigationResult(
        simulated_evidence_used=False,
        refused=True,
        refusal_reason="Insufficient evidence to reach a conclusion.",
    )
    assert refused.refused is True
    assert refused.refusal_reason is not None
    assert refused.observations == []
