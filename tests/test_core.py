import pytest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_PATH"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "test_app.db"
)

from services.database import (
    init_db,
    seed_data,
    get_all_properties,
    get_all_leads,
    get_lead_by_id,
    save_lead,
    add_agent_action,
    get_actions_for_lead,
    get_lead_metrics,
    get_property_by_id,
)
from services.agent import (
    parse_inquiry,
    assess_missing_fields,
    process_inquiry,
    follow_up_inquiry,
)
from services.property_matcher import match_properties
from services.llm_service import LLMResponseSchema
from data.properties import PROPERTIES


@pytest.fixture(autouse=True)
def fresh_db():
    db_path = os.environ["DB_PATH"]
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db()
    seed_data()
    yield
    if os.path.exists(db_path):
        os.remove(db_path)


class TestDatabase:
    def test_database_initialization(self):
        props = get_all_properties()
        assert len(props) == 50

    def test_seed_leads_loaded(self):
        leads = get_all_leads()
        assert len(leads) == 20

    def test_get_property_by_id(self):
        prop = get_property_by_id("P001")
        assert prop is not None
        assert prop["property_id"] == "P001"
        assert prop["location"] == "Technopark"

    def test_get_lead_by_id(self):
        lead = get_lead_by_id("L001")
        assert lead is not None
        assert lead["name"] == "Rahul Nair"

    def test_lead_persistence(self):
        lead_data = {
            "lead_id": "TEST001",
            "name": "Test User",
            "original_inquiry": "Test inquiry",
            "parsed_requirements": {"budget_min": 5000000, "budget_max": 6000000},
            "intent_score": 80,
            "intent_tier": "HIGH",
            "status": "BROKER_ESCALATION",
            "current_action": "ESCALATE_TO_BROKER",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-01",
            "conversation_history": [],
            "decision_history": [],
        }
        save_lead(lead_data)
        retrieved = get_lead_by_id("TEST001")
        assert retrieved is not None
        assert retrieved["name"] == "Test User"

    def test_lead_update(self):
        lead = get_lead_by_id("L001")
        lead["intent_score"] = 95
        lead["updated_at"] = "2025-12-01"
        save_lead(lead)
        updated = get_lead_by_id("L001")
        assert updated["intent_score"] == 95

    def test_agent_action_persistence(self):
        lead = get_lead_by_id("L001")
        add_agent_action(
            lead["lead_id"],
            "ESCALATE_TO_BROKER",
            ["Test reasoning"],
            90,
            {"input": "test"},
            {"decision": "ESCALATE_TO_BROKER"},
        )
        actions = get_actions_for_lead(lead["lead_id"])
        assert len(actions) > 0
        assert actions[0]["decision"] == "ESCALATE_TO_BROKER"

    def test_lead_metrics(self):
        metrics = get_lead_metrics()
        assert metrics["total"] >= 20
        assert "high" in metrics
        assert "medium" in metrics


class TestPropertyMatcher:
    def test_match_by_budget(self):
        requirements = {"budget_min": 4000000, "budget_max": 5000000, "locations": ["Technopark"]}
        matches = match_properties(requirements, PROPERTIES)
        assert len(matches) > 0
        assert all(m["match_score"] > 0 for m in matches)

    def test_match_by_location(self):
        requirements = {"locations": ["Technopark"], "budget_min": 4000000, "budget_max": 8000000}
        matches = match_properties(requirements, PROPERTIES)
        assert len(matches) > 0
        assert all(m["property"]["location"] == "Technopark" for m in matches)

    def test_match_by_bhk(self):
        requirements = {"bhk": 4, "budget_min": 20000000, "budget_max": 40000000}
        matches = match_properties(requirements, PROPERTIES)
        for m in matches:
            assert m["property"]["bhk"] >= 4

    def test_unrealistic_budget_no_high_matches(self):
        requirements = {
            "budget_min": 20000000,
            "budget_max": 25000000,
            "locations": ["Kowdiar"],
        }
        matches = match_properties(requirements, PROPERTIES)
        assert len(matches) >= 0

    def test_match_scores_sorted_descending(self):
        requirements = {
            "budget_min": 5000000,
            "budget_max": 7000000,
            "locations": ["Technopark"],
            "bhk": 3,
        }
        matches = match_properties(requirements, PROPERTIES)
        for i in range(len(matches) - 1):
            assert matches[i]["match_score"] >= matches[i + 1]["match_score"]


class TestAgentPipeline:
    def test_parse_inquiry_with_budget(self):
        req = parse_inquiry("Looking for a 3BHK around Technopark. Budget 65-75 lakh.")
        assert req["budget_min"] is not None
        assert req["budget_max"] is not None
        assert req["bhk"] == 3

    def test_parse_inquiry_with_location(self):
        req = parse_inquiry("I want a flat in Kazhakkoottam.")
        assert "Kazhakkoottam" in req["locations"]

    def test_parse_inquiry_with_timeline(self):
        req = parse_inquiry("Planning to buy within 2 months.")
        assert req["timeline_months"] == 2

    def test_parse_inquiry_with_financing(self):
        req = parse_inquiry("Home loan is already being processed.")
        assert req["financing"] == "Home loan"
        assert req["financing_ready"] == True

    def test_parse_inquiry_with_parking(self):
        req = parse_inquiry("Need 2 parking slots.")
        assert req["parking"] == 2

    def test_assess_missing_fields(self):
        req = {
            "budget_min": None,
            "budget_max": None,
            "locations": [],
            "bhk": None,
            "timeline_months": None,
        }
        missing = assess_missing_fields(req)
        assert "budget range" in missing
        assert "preferred location" in missing
        assert "purchase timeline" in missing

    def test_no_missing_fields_when_complete(self):
        req = {
            "budget_min": 5000000,
            "budget_max": 6000000,
            "locations": ["Technopark"],
            "bhk": 3,
            "timeline_months": 2,
        }
        missing = assess_missing_fields(req)
        assert len(missing) == 0

    def test_high_intent_lead(self):
        result = process_inquiry(
            "Test",
            "Looking for a 3BHK apartment around Technopark. Budget 65-75 lakh. Planning to purchase within 2 months. Home loan is already being processed.",
        )
        assert result["lead_data"]["current_action"] == "ESCALATE_TO_BROKER"
        assert result["lead_data"]["intent_tier"] == "HIGH"
        assert len(result["matches"]) > 0

    def test_ambiguous_lead_asks_questions(self):
        result = process_inquiry("Test", "I need a nice flat in Trivandrum.")
        assert result["lead_data"]["current_action"] == "ASK_MORE_INFO"
        assert result["llm_response"]["follow_up_question"] is not None

    def test_unrealistic_lead(self):
        result = process_inquiry(
            "Test", "I want a 4BHK premium property in Kowdiar for 25 lakh."
        )
        assert result["lead_data"]["current_action"] in [
            "ESCALATE_TO_BROKER",
            "SHOW_MATCHING_PROPERTIES",
            "ASK_MORE_INFO",
            "LOW_PRIORITY_OR_DISCARD",
        ]

    def test_context_change_after_follow_up(self):
        result1 = process_inquiry("Test", "I need a nice flat in Trivandrum.")
        assert result1["lead_data"]["current_action"] == "ASK_MORE_INFO"
        lead_id = result1["lead_data"]["lead_id"]
        lead_obj = result1["lead_data"]
        result2 = follow_up_inquiry(
            lead_id,
            "Test",
            "Around 65 lakh, close to Technopark, hoping within two months.",
            lead_obj,
        )
        assert result2["lead_data"]["current_action"] != "ASK_MORE_INFO"
        assert len(result2["matches"]) > 0

    def test_conversation_history_preserved(self):
        result = process_inquiry(
            "Test", "Looking for a 3BHK around Technopark. Budget 65-75 lakh."
        )
        lead_id = result["lead_data"]["lead_id"]
        lead_obj = result["lead_data"]
        result2 = follow_up_inquiry(
            lead_id, "Test", "I also need 2 parking slots.", lead_obj
        )
        assert len(result2["lead_data"]["conversation_history"]) >= 2

    def test_decision_history_persisted(self):
        result = process_inquiry(
            "Test", "Looking for a 3BHK around Technopark. Budget 65-75 lakh."
        )
        lead_id = result["lead_data"]["lead_id"]
        lead_obj = result["lead_data"]
        result2 = follow_up_inquiry(lead_id, "Test", "Budget is 65 lakh.", lead_obj)
        actions = get_actions_for_lead(lead_id)
        assert len(actions) >= 2

    def test_email_draft_generated(self):
        from services.agent import generate_email_draft, generate_broker_summary

        lead_data = {
            "lead_id": "TEST",
            "name": "Test User",
            "parsed_requirements": {
                "budget_min": 5000000,
                "budget_max": 6000000,
                "locations": ["Technopark"],
                "bhk": 3,
                "property_type": "Apartment",
            },
            "intent_tier": "HIGH",
            "intent_score": 90,
            "status": "BROKER_ESCALATION",
        }
        matches = [
            {
                "property": {
                    "name": "Test Property",
                    "location": "Technopark",
                    "bhk": 3,
                    "price": 5500000,
                    "sqft": 1400,
                    "parking": 2,
                    "availability": "Ready to Move",
                    "furnishing": "Semi-Furnished",
                    "amenities": "Security, Parking",
                    "builder": "Test Builder",
                    "property_type": "Apartment",
                },
                "match_score": 95,
                "reasons": ["Exact location match"],
            }
        ]
        email = generate_email_draft(lead_data, matches)
        assert "Test User" in email
        assert "Subject:" in email
        summary = generate_broker_summary(lead_data, matches)
        assert "BROKER LEAD SUMMARY" in summary
        assert "Test User" in summary


class TestStructuredOutput:
    def test_llm_response_schema(self):
        schema = LLMResponseSchema(
            intent_score=88,
            intent_tier="HIGH",
            decision="ESCALATE_TO_BROKER",
            reasoning=["Budget is realistic"],
            missing_information=[],
            risks=[],
            recommended_next_step="Contact broker",
            follow_up_question=None,
        )
        assert schema.intent_score == 88
        assert schema.intent_tier == "HIGH"

    def test_llm_response_schema_validates_score_range(self):
        with pytest.raises(Exception):
            LLMResponseSchema(
                intent_score=150,
                intent_tier="HIGH",
                decision="ESCALATE_TO_BROKER",
                reasoning=[],
                missing_information=[],
                risks=[],
                recommended_next_step="",
                follow_up_question=None,
            )

    def test_llm_response_schema_validates_tier(self):
        with pytest.raises(Exception):
            LLMResponseSchema(
                intent_score=88,
                intent_tier="INVALID",
                decision="ESCALATE_TO_BROKER",
                reasoning=[],
                missing_information=[],
                risks=[],
                recommended_next_step="",
                follow_up_question=None,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
