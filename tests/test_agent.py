"""The agent pipeline: extraction, context merging, decisions, persistence."""

from __future__ import annotations

import pytest

from conftest import ScriptedProvider, decision_payload, extraction_payload
from models.schemas import LeadRequirements, LeadStatus
from services import agent, drafts
from services.llm_service import LLMCallError


def test_first_turn_persists_lead_conversation_and_decision(temp_db):
    provider = ScriptedProvider([
        extraction_payload(
            name="Rahul Nair", budget_min=6_500_000, budget_max=7_500_000,
            locations=["Technopark", "Kazhakkoottam"], property_type="Apartment",
            bhk=3, timeline_months=2, timeline_text="within 2 months",
            financing_method="Home loan", financing_readiness="IN_PROGRESS",
            parking_required=True, amenities=["Gated Community"], viewing_ready=True,
            purpose="SELF_USE",
        ),
        decision_payload(
            intent_score=90, intent_tier="HIGH", decision="ESCALATE_TO_BROKER",
            reasoning=["Two-month purchase window", "Three strong matches in budget"],
            recommended_next_step="Broker should call today and arrange viewings.",
            summary_headline="Loan-ready 3BHK buyer for the Technopark corridor",
        ),
    ])
    result = agent.run_turn(
        "3BHK near Technopark, 65-75 lakh, buying in 2 months, loan in process.",
        provider=provider,
    )

    assert result.decision.decision.value == "ESCALATE_TO_BROKER"
    assert result.status == LeadStatus.BROKER_ESCALATION.value
    assert result.previous_status == LeadStatus.NEW.value
    assert len(result.matches) >= 3

    lead = temp_db.get_lead(result.lead_id)
    assert lead["intent_tier"] == "HIGH"
    assert lead["status"] == LeadStatus.BROKER_ESCALATION.value
    assert lead["current_action"] == "ESCALATE_TO_BROKER"
    assert lead["requirements"]["budget_max"] == 7_500_000
    assert lead["summary"]["top_matches"]

    turns = temp_db.get_turns(result.lead_id)
    assert [t["role"] for t in turns] == ["buyer", "agent"]

    actions = temp_db.get_actions(result.lead_id)
    assert len(actions) == 1
    assert actions[0]["status_before"] == "NEW"
    assert actions[0]["status_after"] == "BROKER_ESCALATION"
    assert actions[0]["input_snapshot"]["evidence"]["heuristic_score"] > 0
    assert actions[0]["llm_provider"] == "scripted:test"


def test_follow_up_merges_context_and_changes_the_decision(temp_db):
    """Scenario 5: an ambiguous lead becomes escalation-worthy after one answer."""
    provider = ScriptedProvider([
        # Turn 1 - vague.
        extraction_payload(locations=["Trivandrum"], property_type="Apartment"),
        decision_payload(
            intent_score=20, intent_tier="NEEDS_CLARIFICATION", decision="ASK_MORE_INFO",
            reasoning=["No budget stated", "No area or timeline given"],
            missing_information=["Budget range", "Preferred location(s)", "Purchase timeline"],
            recommended_next_step="Clarify budget, area and timeline before broker time.",
            follow_up_question="What budget are you working with, which areas suit you, "
                               "and when are you hoping to buy?",
        ),
        # Turn 2 - the buyer answers. The extractor returns only the new facts;
        # the merge must retain the property type from turn 1.
        extraction_payload(
            budget_min=6_000_000, budget_max=7_000_000,
            locations=["Technopark", "Kazhakkoottam"], bhk=3, timeline_months=2,
            timeline_text="within two months", financing_readiness="IN_PROGRESS",
        ),
        decision_payload(
            intent_score=87, intent_tier="HIGH", decision="ESCALATE_TO_BROKER",
            reasoning=["Budget, area and timeline all arrived in one turn",
                       "Two-month window with financing under way"],
            recommended_next_step="Broker should contact the buyer today.",
        ),
    ])

    first = agent.run_turn("I need a nice flat in Trivandrum.", provider=provider)
    assert first.decision.decision.value == "ASK_MORE_INFO"
    assert first.status == LeadStatus.NEEDS_INFORMATION.value
    assert first.decision.follow_up_question

    second = agent.run_turn(
        "Around 60-70 lakh, close to Technopark, hopefully within two months.",
        lead_id=first.lead_id, provider=provider,
    )

    assert second.lead_id == first.lead_id
    # Context merged: turn-1 property type survived, turn-2 facts were added.
    assert second.requirements.property_type == "Apartment"
    assert second.requirements.budget_max == 7_000_000
    assert second.requirements.bhk == 3
    assert second.requirements.original_inquiry == "I need a nice flat in Trivandrum."
    # The decision visibly changed with the new context.
    assert second.decision.decision.value == "ESCALATE_TO_BROKER"
    assert second.status == LeadStatus.BROKER_ESCALATION.value
    assert second.previous_status == LeadStatus.NEEDS_INFORMATION.value

    assert len(temp_db.get_actions(first.lead_id)) == 2
    assert temp_db.buyer_turn_count(first.lead_id) == 2


def test_merge_keeps_known_values_when_the_model_returns_nothing():
    previous = LeadRequirements(
        budget_max=7_000_000, locations=["Pattom"], bhk=3, property_type="Apartment",
        notes=["relocating"], original_inquiry="first message",
    )
    incoming = LeadRequirements(timeline_months=3, notes=["loan applied"])
    merged = agent._merge_preserving(previous, incoming)
    assert merged.budget_max == 7_000_000
    assert merged.locations == ["Pattom"]
    assert merged.bhk == 3
    assert merged.timeline_months == 3
    assert merged.notes == ["relocating", "loan applied"]
    assert merged.original_inquiry == "first message"


def test_explicit_changes_override_previous_values():
    previous = LeadRequirements(budget_max=5_000_000, locations=["Pattom"], bhk=2)
    incoming = LeadRequirements(budget_max=9_000_000, locations=["Kowdiar"], bhk=3)
    merged = agent._merge_preserving(previous, incoming)
    assert (merged.budget_max, merged.locations, merged.bhk) == (9_000_000, ["Kowdiar"], 3)


def test_invalid_decision_is_retried_then_raises(temp_db):
    bad = decision_payload(decision="SEND_FLOWERS")
    provider = ScriptedProvider([extraction_payload(budget_max=6_000_000), bad, bad])
    with pytest.raises(LLMCallError, match="failed validation twice"):
        agent.run_turn("2BHK for 60 lakh", provider=provider)
    assert provider.payloads == []  # extraction + two decision attempts


def test_decision_retry_succeeds_on_the_second_attempt(temp_db):
    provider = ScriptedProvider([
        extraction_payload(budget_max=6_000_000, locations=["Pattom"], bhk=2),
        decision_payload(decision="NOT_A_REAL_ACTION"),
        decision_payload(decision="SHOW_MATCHING_PROPERTIES"),
    ])
    result = agent.run_turn("2BHK in Pattom for 60 lakh", provider=provider)
    assert result.decision.decision.value == "SHOW_MATCHING_PROPERTIES"
    assert result.status == LeadStatus.QUALIFYING.value


def test_agent_receives_the_evidence_pack_but_no_decision_rule(temp_db):
    """The reasoning prompt must carry evidence, and must not contain thresholds."""
    provider = ScriptedProvider([
        extraction_payload(budget_max=6_000_000, locations=["Pattom"], bhk=2),
        decision_payload(),
    ])
    agent.run_turn("2BHK in Pattom for 60 lakh", provider=provider)
    decision_call = provider.calls[1]
    assert "DETERMINISTIC EVIDENCE" in decision_call["user"]
    assert "heuristic_score" in decision_call["user"]
    assert "not a rule and not a threshold" in decision_call["system"]


def test_unrealistic_lead_reasoning_sees_the_price_floor(temp_db):
    provider = ScriptedProvider([
        extraction_payload(budget_max=2_500_000, locations=["Kowdiar"], bhk=4,
                           property_type="Apartment"),
        decision_payload(
            intent_score=15, intent_tier="LOW", decision="RESET_EXPECTATIONS",
            reasoning=["Cheapest 4BHK in Kowdiar is Rs 2.45 Cr against a Rs 25 L budget",
                       "No inventory can satisfy these requirements"],
            recommended_next_step="Show the real price floor and offer other areas.",
        ),
    ])
    result = agent.run_turn(
        "I want a 4BHK premium property in Kowdiar for 25 lakh.", provider=provider
    )
    assert result.evidence.budget_realism["verdict"] == "UNREALISTIC"
    assert result.evidence.strong_match_count == 0
    assert "2.45 Cr" in provider.calls[1]["user"]
    assert result.status == LeadStatus.QUALIFYING.value


def test_score_divergence_is_flagged(temp_db):
    provider = ScriptedProvider([
        extraction_payload(locations=["Trivandrum"]),
        decision_payload(intent_score=95, intent_tier="HIGH",
                         decision="ESCALATE_TO_BROKER"),
    ])
    result = agent.run_turn("I need a flat", provider=provider)
    assert result.warnings and "diverges" in result.warnings[0]


def test_drafts_are_rendered_and_never_sent(temp_db):
    provider = ScriptedProvider([
        extraction_payload(name="Rahul", budget_max=7_500_000, locations=["Technopark"],
                           bhk=3, timeline_months=2),
        decision_payload(decision="ESCALATE_TO_BROKER", intent_tier="HIGH",
                         intent_score=88, draft_message=None),
    ])
    result = agent.run_turn("3BHK near Technopark under 75 lakh, buying in 2 months",
                            provider=provider)
    draft = drafts.resolve_draft(result.lead_id, result.requirements,
                                 result.decision, result.matches)
    assert draft is not None and draft.audience == "BROKER"
    rendered = drafts.render_draft(draft)
    assert "DRAFT ONLY" in rendered
    assert result.lead_id in rendered


def test_summary_is_structured_and_persisted(temp_db):
    provider = ScriptedProvider([
        extraction_payload(name="Meera", budget_min=6_000_000, budget_max=7_000_000,
                           locations=["Ulloor"], bhk=3, property_type="Apartment",
                           timeline_months=3),
        decision_payload(intent_score=78, intent_tier="HIGH",
                         decision="ESCALATE_TO_BROKER"),
    ])
    result = agent.run_turn("3BHK in Ulloor, 60-70 lakh, 3 months", provider=provider)
    summary = temp_db.get_lead(result.lead_id)["summary"]
    assert summary["name"] == "Meera"
    assert summary["budget"] == "Rs 60 L - Rs 70 L"
    assert summary["timeline"] == "~3 months"
    assert summary["decision"] == "ESCALATE_TO_BROKER"
    assert summary["intent_score"] == 78
    assert len(summary["top_matches"]) <= 3


def test_empty_message_is_rejected(temp_db):
    with pytest.raises(ValueError):
        agent.run_turn("   ", provider=ScriptedProvider([]))
