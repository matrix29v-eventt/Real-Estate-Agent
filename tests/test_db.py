"""Database initialisation, seeding and persistence."""

from __future__ import annotations

from models.schemas import LeadStatus


def test_schema_and_seed(temp_db):
    db = temp_db
    assert db.count_rows("properties") >= 40
    assert 15 <= db.count_rows("leads") <= 25
    assert db.count_rows("agent_actions") == db.count_rows("leads")


def test_seeding_is_idempotent(temp_db):
    db = temp_db
    before = db.count_rows("properties")
    db.ensure_seeded()  # second call must not duplicate
    assert db.count_rows("properties") == before


def test_property_rows_decode_lists(temp_db):
    prop = temp_db.get_properties(["P001"])[0]
    assert isinstance(prop["amenities"], list) and prop["amenities"]
    assert isinstance(prop["tags"], list) and "technopark-nearby" in prop["tags"]
    assert prop["parking"] is True


def test_dataset_has_realistic_gaps(temp_db):
    """The inventory must not trivially satisfy every inquiry."""
    props = temp_db.list_properties()
    assert min(p["price"] for p in props if p["bhk"] == 4) > 10_000_000
    assert min(p["price"] for p in props if p["location"] == "Kowdiar") > 5_000_000
    assert any(p["availability"] != "AVAILABLE" for p in props)
    assert any(p["possession_status"] == "Under Construction" for p in props)


def test_lead_lifecycle(temp_db):
    db = temp_db
    lead_id = db.create_lead(name="Test Buyer", original_inquiry="2BHK in Pattom")
    assert lead_id.startswith("L")

    db.update_lead(
        lead_id,
        requirements={"budget_max": 6_000_000, "locations": ["Pattom"]},
        intent_score=72,
        intent_tier="MEDIUM",
        status=LeadStatus.QUALIFYING.value,
        current_action="SHOW_MATCHING_PROPERTIES",
    )
    lead = db.get_lead(lead_id)
    assert lead["requirements"]["budget_max"] == 6_000_000
    assert lead["intent_score"] == 72
    assert lead["status"] == LeadStatus.QUALIFYING.value
    assert lead["updated_at"] >= lead["created_at"]


def test_conversation_turn_ordering(temp_db):
    db = temp_db
    lead_id = db.create_lead(original_inquiry="hello")
    db.add_turn(lead_id, "buyer", "first")
    db.add_turn(lead_id, "agent", "second")
    db.add_turn(lead_id, "buyer", "third")
    turns = db.get_turns(lead_id)
    assert [t["turn_index"] for t in turns] == [0, 1, 2]
    assert [t["message"] for t in turns] == ["first", "second", "third"]
    assert db.buyer_turn_count(lead_id) == 2


def test_agent_action_audit_trail(temp_db):
    db = temp_db
    lead_id = db.create_lead(original_inquiry="hello")
    db.record_action(
        lead_id=lead_id,
        decision="ESCALATE_TO_BROKER",
        intent_score=88,
        intent_tier="HIGH",
        reasoning=["urgent", "budget fits"],
        input_snapshot={"requirements": {"bhk": 3}},
        output_snapshot={"decision": "ESCALATE_TO_BROKER"},
        status_before="NEW",
        status_after="BROKER_ESCALATION",
        llm_provider="scripted:test",
    )
    actions = db.get_actions(lead_id)
    assert len(actions) == 1
    action = actions[0]
    assert action["reasoning"] == ["urgent", "budget fits"]
    assert action["input_snapshot"]["requirements"]["bhk"] == 3
    assert action["status_before"] == "NEW"
    assert action["status_after"] == "BROKER_ESCALATION"


def test_dashboard_metrics(temp_db):
    metrics = temp_db.dashboard_metrics()
    assert metrics["total_leads"] == temp_db.count_rows("leads")
    assert metrics["high_intent"] > 0
    assert metrics["broker_escalations"] > 0
    assert metrics["needs_clarification"] > 0


def test_next_lead_id_increments(temp_db):
    db = temp_db
    first = db.next_lead_id()
    db.create_lead(lead_id=first, original_inquiry="x")
    assert db.next_lead_id() != first
