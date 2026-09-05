"""Validation of the structured agent output contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.schemas import (
    ACTION_TO_STATUS,
    AgentDecision,
    LeadRequirements,
    LeadStatus,
    NextAction,
    money,
    parse_rupees,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("65 lakh", 6_500_000),
        ("1.2 crore", 12_000_000),
        ("6500000", 6_500_000),
        (65, 6_500_000),
        ("25L", 2_500_000),
        ("1,20,00,000", 12_000_000),
        (None, None),
        ("", None),
        ("not a number", None),
    ],
)
def test_budget_parsing(raw, expected):
    assert parse_rupees(raw) == expected


def test_requirement_coercion_is_forgiving_but_typed():
    req = LeadRequirements(
        budget_max="70 lakh", locations="Technopark", bhk="3",
        timeline_months="2", financing_readiness="in progress", purpose="self use",
    )
    assert req.budget_max == 7_000_000
    assert req.locations == ["Technopark"]
    assert req.bhk == 3
    assert req.timeline_months == 2.0
    assert req.financing_readiness.value == "IN_PROGRESS"
    assert req.purpose.value == "SELF_USE"


def test_unknown_enum_values_fall_back_rather_than_crash():
    req = LeadRequirements(financing_readiness="maybe someday", purpose="???")
    assert req.financing_readiness.value == "UNKNOWN"
    assert req.purpose.value == "UNKNOWN"


def test_budget_and_timeline_labels():
    req = LeadRequirements(budget_min=6_000_000, budget_max=7_000_000, timeline_months=2)
    assert req.budget_label() == "Rs 60 L - Rs 70 L"
    assert req.timeline_label() == "~2 months"
    assert LeadRequirements().budget_label() == "Not stated"
    assert money(12_000_000) == "Rs 1.20 Cr"


def test_valid_decision_maps_to_a_status():
    decision = AgentDecision(
        intent_score=88, intent_tier="HIGH", decision="ESCALATE_TO_BROKER",
        reasoning=["urgent", "budget fits"],
        recommended_next_step="Call today.",
    )
    assert decision.status == LeadStatus.BROKER_ESCALATION.value
    assert set(ACTION_TO_STATUS) == {a.value for a in NextAction}


def test_malformed_decisions_are_rejected():
    with pytest.raises(ValidationError):  # unknown action
        AgentDecision(intent_score=50, intent_tier="HIGH", decision="CALL_THE_POLICE",
                      reasoning=["x"], recommended_next_step="y")
    with pytest.raises(ValidationError):  # empty reasoning
        AgentDecision(intent_score=50, intent_tier="HIGH", decision="NURTURE_LEAD",
                      reasoning=[], recommended_next_step="y")
    with pytest.raises(ValidationError):  # missing required field
        AgentDecision(intent_score=50, intent_tier="HIGH", decision="NURTURE_LEAD",
                      reasoning=["x"])


def test_out_of_range_values_are_clamped_not_crashed():
    decision = AgentDecision(
        intent_score=140, intent_tier="LOW", decision="NURTURE_LEAD",
        reasoning="single string becomes a list", recommended_next_step="y",
        confidence=5.0, follow_up_question="   ",
    )
    assert decision.intent_score == 100
    assert decision.reasoning == ["single string becomes a list"]
    assert decision.confidence == 1.0
    assert decision.follow_up_question is None
