import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from services.database import (
    get_db,
    seed_data,
    save_lead,
    add_conversation,
    add_agent_action,
    get_property_by_id,
)
from services.property_matcher import match_properties
from services.llm_service import llm_reasoning, LLMResponseSchema
from data.properties import PROPERTIES
from data.leads import SEED_LEADS

INITIAL_REQUIREMENTS = {
    "budget_min": None,
    "budget_max": None,
    "locations": [],
    "bhk": None,
    "parking": None,
    "furnishing": None,
    "timeline_months": None,
    "financing": None,
    "financing_ready": False,
    "amenities": [],
    "purpose": None,
    "viewing_ready": False,
    "min_sqft": None,
    "property_type": None,
}


def parse_inquiry(inquiry_text: str) -> Dict[str, Any]:
    requirements = dict(INITIAL_REQUIREMENTS)
    inquiry_lower = inquiry_text.lower()

    budget_keywords = {
        "20 lakh": 2000000,
        "25 lakh": 2500000,
        "30 lakh": 3000000,
        "35 lakh": 3500000,
        "40 lakh": 4000000,
        "45 lakh": 4500000,
        "50 lakh": 5000000,
        "55 lakh": 5500000,
        "60 lakh": 6000000,
        "65 lakh": 6500000,
        "70 lakh": 7000000,
        "75 lakh": 7500000,
        "80 lakh": 8000000,
        "85 lakh": 8500000,
        "90 lakh": 9000000,
        "1 crore": 10000000,
        "1.5 crore": 15000000,
        "2 crore": 20000000,
        "2.5 crore": 25000000,
        "3 crore": 30000000,
    }

    for kw, val in budget_keywords.items():
        if kw in inquiry_lower:
            if (
                "budget" in inquiry_lower
                or "around" in inquiry_lower
                or "crore" in inquiry_lower
                or "lakh" in inquiry_lower
            ):
                if "lakh" in kw or "crore" in kw:
                    if requirements["budget_min"] is None:
                        requirements["budget_min"] = val * 0.8
                        requirements["budget_max"] = val * 1.2
                    else:
                        requirements["budget_min"] = min(
                            requirements["budget_min"], val * 0.8
                        )
                        requirements["budget_max"] = max(
                            requirements["budget_max"], val * 1.2
                        )

    bhk_match = None
    for bhk_num in [1, 2, 3, 4, 5]:
        if f"{bhk_num}bhk" in inquiry_lower or f"{bhk_num} bhk" in inquiry_lower:
            bhk_match = bhk_num
    if bhk_match:
        requirements["bhk"] = bhk_match

    locations = []
    location_map = {
        "technopark": "Technopark",
        "kazhakkoottam": "Kazhakkoottam",
        "sreekaryam": "Sreekaryam",
        "akkulam": "Akkulam",
        "ulloor": "Ulloor",
        "pattom": "Pattom",
        "kowdiar": "Kowdiar",
        "vazhuthacaud": "Vazhuthacaud",
        "peroorkada": "Peroorkada",
        "kesavadasapuram": "Kesavadasapuram",
        "thampanoor": "Thampanoor",
        "poojappura": "Poojappura",
        "trivandrum": None,
    }
    for loc_key, loc_val in location_map.items():
        if loc_key in inquiry_lower:
            if loc_val:
                locations.append(loc_val)

    location_aliases = {
        "kazhakkoottam": [
            "kazhakkoottam",
            "kazhakoottam",
            "kazhakootam",
            "kzakkoottam",
        ],
        "kozhikode": ["kozhikode", "calicut"],
    }
    for loc_key, aliases in location_aliases.items():
        if loc_key in inquiry_lower and loc_key not in locations:
            if location_map[loc_key]:
                locations.append(location_map[loc_key])
        for alias in aliases:
            if alias in inquiry_lower:
                if location_map[loc_key]:
                    locations.append(location_map[loc_key])

    if "trivandrum" in inquiry_lower and not locations:
        pass

    if locations:
        requirements["locations"] = list(set(locations))

    parking_match = None
    parking_phrases = [
        "2 parking",
        "two parking",
        "need parking",
        "parking required",
        "parking needed",
    ]
    for phrase in parking_phrases:
        if phrase in inquiry_lower:
            parking_match = 2 if "2" in phrase or "two" in phrase else 1
            break
    if "parking" in inquiry_lower and parking_match is None:
        parking_match = 1
    if parking_match:
        requirements["parking"] = parking_match

    timeline_match = None
    timeline_phrases = {
        "within 1 month": 1,
        "1 month": 1,
        "within 2 months": 2,
        "2 months": 2,
        "within 3 months": 3,
        "3 months": 3,
        "within 45 days": 1.5,
        "within 6 months": 6,
        "6 months": 6,
        "within a year": 12,
        "18 months": 18,
        "within 18 months": 18,
        "18 months": 18,
        "within 12 months": 12,
        "12 months": 12,
    }
    for phrase, months in timeline_phrases.items():
        if phrase in inquiry_lower:
            timeline_match = months
            break
    if timeline_match is not None:
        requirements["timeline_months"] = timeline_match

    financing_keywords = [
        "home loan",
        "home loan process",
        "loan approved",
        "loan cleared",
        "loan processing",
        "home loan being processed",
        "home loan process started",
        "loan process started",
    ]
    for kw in financing_keywords:
        if kw in inquiry_lower:
            requirements["financing"] = "Home loan"
            requirements["financing_ready"] = True
            break

    furnishing_keywords = {
        "unfurnished": "Unfurnished",
        "furnished": "Furnished",
        "semi-furnished": "Semi-Furnished",
        "fully furnished": "Fully Furnished",
    }
    for kw, val in furnishing_keywords.items():
        if kw in inquiry_lower:
            requirements["furnishing"] = val
            break

    if (
        "investment" in inquiry_lower
        or "rental" in inquiry_lower
        or "invest" in inquiry_lower
    ):
        requirements["purpose"] = "investment"
    elif (
        "self-use" in inquiry_lower
        or "own" in inquiry_lower
        or "parents" in inquiry_lower
        or "family" in inquiry_lower
    ):
        requirements["purpose"] = "self-use"

    if "ready to move" in inquiry_lower or "immediate possession" in inquiry_lower:
        requirements["availability"] = "Ready"

    if "gated community" in inquiry_lower:
        requirements["amenities"].append("gated community")
    if "garden" in inquiry_lower:
        requirements["amenities"].append("garden")
    if "swimming pool" in inquiry_lower:
        requirements["amenities"].append("swimming pool")
    if "gym" in inquiry_lower:
        requirements["amenities"].append("gym")
    if "elevator" in inquiry_lower or "lift" in inquiry_lower:
        requirements["amenities"].append("elevator")

    if (
        "viewing" in inquiry_lower
        or "schedule" in inquiry_lower
        or "visit" in inquiry_lower
    ):
        requirements["viewing_ready"] = True

    return requirements


def assess_missing_fields(requirements: Dict[str, Any]) -> List[str]:
    missing = []
    if not requirements.get("budget_min") or not requirements.get("budget_max"):
        missing.append("budget range")
    if len(requirements.get("locations", [])) == 0:
        missing.append("preferred location")
    if requirements.get("timeline_months") is None:
        missing.append("purchase timeline")
    if requirements.get("bhk") is None:
        missing.append("property type/BHK")
    return missing


def analyze_lead(
    name: str,
    inquiry_text: str,
    requirements: Dict[str, Any],
    conversation_history: List[Dict],
    lead_id: Optional[str] = None,
    existing_lead: Optional[Dict] = None,
) -> Dict[str, Any]:
    if existing_lead:
        req = existing_lead.get("parsed_requirements", requirements)
        for key in requirements:
            if (
                requirements[key] is not None
                and requirements[key] != []
                and requirements[key] != False
            ):
                req[key] = requirements[key]
        requirements = req

    if not lead_id:
        from services.database import get_all_leads

        all_leads = get_all_leads()
        next_num = len(all_leads) + 1
        lead_id = f"L{next_num:03d}"

    matches = []
    has_enough_info = (
        requirements.get("budget_min")
        and requirements.get("budget_max")
        and len(requirements.get("locations", [])) > 0
    )

    if has_enough_info:
        matches = match_properties(requirements, PROPERTIES)

    missing_fields = assess_missing_fields(requirements) if not has_enough_info else []

    if has_enough_info and not missing_fields:
        missing_fields = assess_missing_fields(requirements)

    lead_context = {
        "name": name,
        "original_inquiry": inquiry_text,
        "budget_min": requirements.get("budget_min"),
        "budget_max": requirements.get("budget_max"),
        "locations": requirements.get("locations", []),
        "bhk": requirements.get("bhk"),
        "timeline_months": requirements.get("timeline_months"),
        "financing": requirements.get("financing"),
        "financing_ready": requirements.get("financing_ready", False),
        "parking": requirements.get("parking"),
        "furnishing": requirements.get("furnishing"),
        "amenities": requirements.get("amenities", []),
        "purpose": requirements.get("purpose"),
        "viewing_ready": requirements.get("viewing_ready", False),
        "conversation_history": conversation_history,
    }

    llm_response = llm_reasoning(lead_context, matches, missing_fields)

    intent_score = llm_response.intent_score
    intent_tier = llm_response.intent_tier
    decision = llm_response.decision
    reasoning = llm_response.reasoning
    missing_information = llm_response.missing_information
    risks = llm_response.risks
    recommended_next_step = llm_response.recommended_next_step
    follow_up_question = llm_response.follow_up_question

    if not has_enough_info and decision != "ASK_MORE_INFO":
        decision = "ASK_MORE_INFO"
        reasoning.append("Insufficient critical information for final decision")
        if not follow_up_question:
            follow_up_question = "Could you provide your budget range, preferred location, and purchase timeline?"

    if intent_tier == "NEEDS_CLARIFICATION":
        intent_tier = "MEDIUM"

    status_map = {
        "ESCALATE_TO_BROKER": "BROKER_ESCALATION",
        "SHOW_MATCHING_PROPERTIES": "SHOW_MATCHING",
        "ASK_MORE_INFO": "NEEDS_INFORMATION",
        "NURTURE_LEAD": "NURTURE",
        "LOW_PRIORITY_OR_DISCARD": "LOW_PRIORITY",
    }
    status = status_map.get(decision, "NEW")

    updated_requirements = dict(requirements)
    updated_requirements["amenities"] = requirements.get("amenities", [])

    lead_data = {
        "lead_id": lead_id,
        "name": name,
        "original_inquiry": inquiry_text,
        "parsed_requirements": updated_requirements,
        "intent_score": intent_score,
        "intent_tier": intent_tier,
        "status": status,
        "current_action": decision,
        "created_at": existing_lead.get("created_at", datetime.now().isoformat())
        if existing_lead
        else datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "conversation_history": conversation_history,
        "decision_history": existing_lead.get("decision_history", [])
        if existing_lead
        else [],
    }

    if existing_lead:
        lead_data["decision_history"] = existing_lead.get("decision_history", []) + [
            {
                "action": decision,
                "timestamp": datetime.now().isoformat(),
                "reasoning": reasoning,
                "intent_score": intent_score,
            }
        ]
    else:
        lead_data["decision_history"] = [
            {
                "action": decision,
                "timestamp": datetime.now().isoformat(),
                "reasoning": reasoning,
                "intent_score": intent_score,
            }
        ]

    return {
        "lead_data": lead_data,
        "matches": matches,
        "llm_response": {
            "intent_score": intent_score,
            "intent_tier": intent_tier,
            "decision": decision,
            "reasoning": reasoning,
            "missing_information": missing_information,
            "risks": risks,
            "recommended_next_step": recommended_next_step,
            "follow_up_question": follow_up_question,
        },
        "missing_fields": missing_fields,
        "has_enough_info": has_enough_info,
    }


def process_inquiry(
    name: str,
    inquiry_text: str,
    conversation_history: List[Dict] = None,
    lead_id: str = None,
    existing_lead: Dict = None,
) -> Dict[str, Any]:
    seed_data()
    conversation_history = list(conversation_history or [])
    conversation_history.append(
        {
            "sender": "buyer",
            "message": inquiry_text,
            "timestamp": datetime.now().isoformat(),
        }
    )

    requirements = parse_inquiry(inquiry_text)

    result = analyze_lead(
        name, inquiry_text, requirements, conversation_history, lead_id, existing_lead
    )

    lead_data = result["lead_data"]

    save_lead(lead_data)
    add_conversation(
        lead_data["lead_id"], "buyer", inquiry_text, len(conversation_history) + 1
    )
    add_agent_action(
        lead_data["lead_id"],
        lead_data["current_action"],
        result["llm_response"]["reasoning"],
        lead_data["intent_score"],
        {"inquiry": inquiry_text, "requirements": requirements},
        result["llm_response"],
    )

    result["lead_data"] = lead_data
    return result


def follow_up_inquiry(
    lead_id: str, name: str, answer_text: str, existing_lead: Dict
) -> Dict[str, Any]:
    seed_data()
    conversation_history = list(existing_lead.get("conversation_history", []))
    conversation_history.append(
        {
            "sender": "buyer",
            "message": answer_text,
            "timestamp": datetime.now().isoformat(),
        }
    )

    requirements = dict(existing_lead.get("parsed_requirements", {}))
    new_reqs = parse_inquiry(answer_text)
    for key in new_reqs:
        if new_reqs[key] is not None and new_reqs[key] != [] and new_reqs[key] != False:
            requirements[key] = new_reqs[key]

    result = analyze_lead(
        name, answer_text, requirements, conversation_history, lead_id, existing_lead
    )

    lead_data = result["lead_data"]
    lead_data["conversation_history"] = list(conversation_history)
    if result["llm_response"]["follow_up_question"]:
        lead_data["conversation_history"].append(
            {
                "sender": "agent",
                "message": result["llm_response"]["follow_up_question"],
                "timestamp": datetime.now().isoformat(),
            }
        )
    save_lead(lead_data)
    add_conversation(
        lead_data["lead_id"], "buyer", answer_text, len(conversation_history)
    )
    if result["llm_response"]["follow_up_question"]:
        add_conversation(
            lead_data["lead_id"],
            "agent",
            result["llm_response"]["follow_up_question"],
            len(conversation_history) + 1,
        )
    add_agent_action(
        lead_data["lead_id"],
        lead_data["current_action"],
        result["llm_response"]["reasoning"],
        lead_data["intent_score"],
        {"answer": answer_text, "requirements": requirements},
        result["llm_response"],
    )

    result["lead_data"] = lead_data
    return result


def generate_email_draft(lead_data: Dict, matches: List[Dict]) -> str:
    name = lead_data.get("name", " valued customer")
    req = lead_data.get("parsed_requirements", {})
    budget_min = req.get("budget_min")
    budget_max = req.get("budget_max")
    if budget_min and budget_max:
        budget_str = f"₹{budget_min / 100000:.1f} - ₹{budget_max / 100000:.1f} Lakh"
    else:
        budget_str = "TBD"
    locations = (
        ", ".join(lead_data.get("parsed_requirements", {}).get("locations", []))
        or "TBD"
    )
    bhk = lead_data.get("parsed_requirements", {}).get("bhk", "TBD")

    top_match = matches[0]["property"] if matches else None

    if top_match:
        body = f"""Subject: Property Match Found - {bhk}BHK in {locations}

Dear {name},

Thank you for your inquiry. Based on your requirements, I have identified the following property that closely matches your criteria:

Property: {top_match["name"]}
Location: {top_match["location"]}
Type: {top_match["property_type"]} ({top_match["bhk"]}BHK)
Price: ₹{top_match["price"] / 100000:.1f} Lakh
Size: {top_match["sqft"]} sqft
Parking: {top_match["parking"]} slots
Availability: {top_match["availability"]}
Furnishing: {top_match["furnishing"]}
Amenities: {top_match["amenities"]}
Builder: {top_match["builder"]}

This property falls within your budget of {budget_str} and is located in your preferred area.

Would you like to schedule a viewing? I am available at your convenience.

Best regards,
Property Agent"""
    else:
        body = f"""Subject: Your Property Requirements - Follow-up

Dear {name},

Thank you for your interest. Based on your requirements (Budget: {budget_str}, Location: {locations}, {bhk}BHK), we are currently searching for properties that closely match your criteria.

We will get back to you shortly with suitable options.

Best regards,
Property Agent"""

    return body


def generate_broker_summary(lead_data: Dict, matches: List[Dict]) -> str:
    name = lead_data.get("name", "Unknown")
    req = lead_data.get("parsed_requirements", {})
    budget = (
        req.get("budget_min")
        and req.get("budget_max")
        and f"₹{req['budget_min'] / 100000:.1f}-{req['budget_max'] / 100000:.1f}L"
        or "TBD"
    )
    locations = ", ".join(req.get("locations", [])) or "TBD"
    timeline = req.get("timeline_months", "TBD")
    financing = "Yes" if req.get("financing_ready") else "No"

    match_list = (
        "\n".join(
            [
                f"  - {m['property']['name']} ({m['match_score']}% match)"
                for m in matches[:3]
            ]
        )
        if matches
        else "  None found"
    )

    summary = f"""BROKER LEAD SUMMARY
====================
Lead ID: {lead_data["lead_id"]}
Name: {name}
Intent: {lead_data["intent_tier"]} ({lead_data["intent_score"]}/100)
Status: {lead_data["status"]}

REQUIREMENTS:
Budget: {budget}
Location: {locations}
BHK: {req.get("bhk", "TBD")}
Timeline: {timeline} months
Financing Ready: {financing}

TOP PROPERTY MATCHES:
{match_list}

ACTION: Prioritize broker follow-up and arrange property viewing.
"""
    return summary
