"""Deterministic evidence: missing information, contradictions, scoring."""

from __future__ import annotations

import pytest

from models.schemas import LeadRequirements
from services import matcher, signals


@pytest.fixture()
def props(temp_db):
    return temp_db.list_properties()


def _evidence(req, props, **kwargs):
    matches = matcher.match_properties(req, props)
    return signals.compute_evidence(req, matches, props, **kwargs)


def test_vague_inquiry_flags_every_critical_field(props):
    req = LeadRequirements(locations=["Trivandrum"], property_type="Apartment")
    evidence = _evidence(req, props)
    assert set(evidence.missing_critical_fields) == {
        "Budget range", "Preferred location(s)", "Purchase timeline"
    }
    assert evidence.completeness_pct < 25
    assert evidence.heuristic_score < 30
    # Matching a whole catalogue against a vague request proves nothing.
    assert evidence.inventory_stats["matching_is_meaningful"] is False
    assert evidence.strong_match_count == 0


def test_complete_urgent_lead_scores_high(props):
    req = LeadRequirements(
        budget_min=6_500_000, budget_max=7_500_000,
        locations=["Technopark", "Kazhakkoottam"], property_type="Apartment", bhk=3,
        timeline_months=2, financing_readiness="APPROVED", parking_required=True,
        amenities=["Gated Community"], viewing_ready=True, purpose="SELF_USE",
        contact="buyer@example.com",
    )
    evidence = _evidence(req, props)
    assert evidence.missing_critical_fields == []
    assert evidence.heuristic_score >= 80
    assert evidence.strong_match_count >= 3
    assert evidence.budget_realism["verdict"] == "REALISTIC"


def test_unrealistic_budget_is_penalised_with_evidence(props):
    req = LeadRequirements(budget_max=2_500_000, locations=["Kowdiar"], bhk=4,
                           property_type="Apartment", timeline_months=2)
    evidence = _evidence(req, props)
    assert evidence.budget_realism["verdict"] == "UNREALISTIC"
    assert evidence.score_breakdown["unrealistic_budget"] == -25
    assert evidence.strong_match_count == 0
    assert evidence.heuristic_score < 40


def test_long_timeline_lowers_urgency_points(props):
    near = LeadRequirements(budget_max=8_000_000, locations=["Ulloor"], bhk=3,
                            property_type="Apartment", timeline_months=2)
    far = near.model_copy(update={"timeline_months": 18})
    assert (_evidence(near, props).score_breakdown["timeline_urgency"]
            > _evidence(far, props).score_breakdown["timeline_urgency"])


def test_contradiction_detection():
    previous = LeadRequirements(budget_max=5_000_000, locations=["Pattom"], bhk=2)
    current = LeadRequirements(budget_max=15_000_000, locations=["Kowdiar"], bhk=4)
    notes = signals.detect_contradictions(current, previous.model_dump())
    assert len(notes) == 3
    assert any("Budget moved" in n for n in notes)
    assert any("areas changed" in n for n in notes)
    assert any("Configuration changed" in n for n in notes)


def test_adding_information_is_not_a_contradiction():
    previous = LeadRequirements(locations=["Pattom"])
    current = LeadRequirements(locations=["Pattom"], budget_max=6_000_000, bhk=3)
    assert signals.detect_contradictions(current, previous.model_dump()) == []


def test_repeated_vagueness_is_penalised(props):
    req = LeadRequirements(property_type="Apartment")
    evidence = _evidence(req, props, conversation_turns=3)
    assert evidence.score_breakdown["still_vague_after_clarification"] == -10
