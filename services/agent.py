"""The lead qualification agent.

Pipeline for a single turn:

    buyer message + stored lead context
      -> [LLM]  understanding / extraction with context merge
      -> [code] deterministic property matching
      -> [code] deterministic evidence pack (completeness, realism, contradictions,
                heuristic score)
      -> [LLM]  qualification + next-action reasoning over the whole picture
      -> [code] validation, persistence, status transition, audit trail
      -> structured lead summary

Two LLM calls per turn, deliberately. The first is a parsing task, the second is
the judgement task. Everything mechanical in between is plain Python, and the
heuristic score it produces is handed to the agent as *evidence* - the agent is
explicitly told it is not a threshold.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from models.schemas import (
    AgentDecision,
    EvidencePack,
    LeadRequirements,
    LeadStatus,
    PropertyMatch,
    TurnResult,
    money,
    utc_now,
)
from services import db, llm_service, matcher, signals
from services.llm_service import LLMCallError, LLMProvider, LLMUnavailable

# --------------------------------------------------------------------------- #
# JSON schemas for structured model output
# --------------------------------------------------------------------------- #
_STR = {"type": ["string", "null"]}
_INT = {"type": ["integer", "null"]}
_NUM = {"type": ["number", "null"]}
_BOOL = {"type": ["boolean", "null"]}
_STRLIST = {"type": "array", "items": {"type": "string"}}

EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": _STR,
        "contact": _STR,
        "budget_min": {**_INT, "description": "Lower bound in whole rupees"},
        "budget_max": {**_INT, "description": "Upper bound in whole rupees"},
        "locations": _STRLIST,
        "property_type": {"type": ["string", "null"],
                          "enum": ["Apartment", "Villa", "Plot", "Builder Floor", None]},
        "bhk": _INT,
        "min_sqft": _INT,
        "timeline_months": {**_NUM, "description": "Months until intended purchase"},
        "timeline_text": _STR,
        "financing_method": _STR,
        "financing_readiness": {"type": "string",
                                "enum": ["APPROVED", "IN_PROGRESS", "NOT_STARTED", "UNKNOWN"]},
        "amenities": _STRLIST,
        "parking_required": _BOOL,
        "furnishing": {"type": ["string", "null"],
                       "enum": ["Unfurnished", "Semi-Furnished", "Fully-Furnished", None]},
        "purpose": {"type": "string", "enum": ["SELF_USE", "INVESTMENT", "UNKNOWN"]},
        "viewing_ready": _BOOL,
        "notes": _STRLIST,
    },
    "required": [
        "name", "contact", "budget_min", "budget_max", "locations", "property_type",
        "bhk", "min_sqft", "timeline_months", "timeline_text", "financing_method",
        "financing_readiness", "amenities", "parking_required", "furnishing",
        "purpose", "viewing_ready", "notes",
    ],
}

DECISION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "intent_tier": {"type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW", "NEEDS_CLARIFICATION"]},
        "decision": {"type": "string",
                     "enum": ["ASK_MORE_INFO", "SHOW_MATCHING_PROPERTIES",
                              "ESCALATE_TO_BROKER", "NURTURE_LEAD",
                              "RESET_EXPECTATIONS", "LOW_PRIORITY_OR_DISCARD"]},
        "reasoning": {"type": "array", "items": {"type": "string"},
                      "minItems": 2, "maxItems": 6},
        "missing_information": _STRLIST,
        "risks": _STRLIST,
        "recommended_next_step": {"type": "string"},
        "follow_up_question": _STR,
        "summary_headline": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "draft_message": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "audience": {"type": "string", "enum": ["BROKER", "BUYER"]},
                "channel": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["audience", "channel", "subject", "body"],
        },
    },
    "required": [
        "intent_score", "intent_tier", "decision", "reasoning", "missing_information",
        "risks", "recommended_next_step", "follow_up_question", "summary_headline",
        "confidence", "draft_message",
    ],
}


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
EXTRACTION_SYSTEM = """\
You are the understanding stage of a real estate lead qualification agent working
the Thiruvananthapuram (Trivandrum), Kerala market.

Your job is to read the buyer's newest message together with everything already
known about them, and return the COMPLETE merged picture of their requirements.

Rules:
- Merge, never reset. Carry forward every previously known value unless the new
  message actually changes it. If the buyer contradicts an earlier statement,
  use the newer value and record the change in `notes`.
- Extract only what the buyer said or clearly implied. Never invent a budget,
  area or timeline that was not stated. Unknown fields must be null / empty.
- Budgets are whole rupees. "65 lakh" is 6500000. "1.2 crore" is 12000000.
  A range like "60-70 lakh" fills both budget_min and budget_max; a single
  ceiling like "under 60 lakh" fills only budget_max.
- `timeline_months` is a number of months ("within two months" -> 2,
  "next year" -> 12, "18 months" -> 18). Keep the buyer's own words in
  `timeline_text`.
- `locations` must use recognisable Trivandrum area names when the buyer names
  one. If the buyer only says "Trivandrum" or "anywhere in the city", record
  exactly that - do not guess specific areas.
- Landmarks count as locations: "near Technopark" -> ["Technopark"].
- `financing_readiness`: APPROVED when a loan is sanctioned/pre-approved or the
  buyer is paying cash with funds ready; IN_PROGRESS when applied for or under
  process; NOT_STARTED when they say they have not begun; otherwise UNKNOWN.
- `viewing_ready` is true only if the buyer indicates willingness to visit.
- `notes` holds short factual observations that do not fit another field
  (relocation deadlines, family size, contradictions, stated flexibility).

Known areas: {areas}

Return only the JSON object.
"""

DECISION_SYSTEM = """\
You are the routing brain of a real estate lead qualification agent. A broker's
time is the scarce resource. Your judgement decides who gets it.

You receive:
1. The merged buyer requirements.
2. A deterministic evidence pack (completeness, missing fields, budget realism
   against real inventory, contradictions across turns, and a heuristic score).
3. The top deterministic property matches from the live inventory.
4. The conversation so far.

How to reason:
- Weigh the WHOLE situation. The heuristic score is one piece of evidence
  computed by a fixed rubric; it is not a rule and not a threshold. It is
  routinely right about clarity and wrong about context. Where the score and the
  situation disagree, follow the situation and say so in your reasoning.
- Ask yourself what a good broker would actually do next with this person today.
- Urgency, financing readiness and whether real inventory exists usually matter
  more than how many fields happen to be filled in.
- A buyer with a serious timeline but a fixable information gap is worth
  clarifying. A buyer with perfect information and no intention of buying for
  two years is not worth a call today.
- Never invent properties. Only reference `property_id` values you were given.
- If no property in the list genuinely fits, say so plainly rather than
  presenting weak matches as options.

Available actions:
- ASK_MORE_INFO - critical context is missing and one good question would unlock
  the lead. Set `follow_up_question` to a single natural, specific question that
  acknowledges what the buyer already told you. Never re-ask something known.
- SHOW_MATCHING_PROPERTIES - enough is known to be useful, but not yet enough to
  justify broker time; share the shortlist and keep qualifying.
- ESCALATE_TO_BROKER - a human should contact this buyer now. Justify the
  urgency, the budget/inventory fit, and what the broker should do first.
- NURTURE_LEAD - genuine but not near-term; keep warm on a schedule.
- RESET_EXPECTATIONS - what the buyer wants does not exist at their budget; the
  honest next step is to show them the real price floor and offer alternatives.
- LOW_PRIORITY_OR_DISCARD - no purchase signal worth pursuing.

Mistakes to avoid:
- Do not ask for information the buyer has already given. Check the requirements
  and the transcript first.
- ASK_MORE_INFO is for a genuine gap. If `missing_critical_fields` is empty, more
  questions delay someone who has already told you what matters; pick the action
  that moves the deal instead.
- More questions cannot fix arithmetic. When `budget_realism.verdict` is
  UNREALISTIC and nothing viable exists, the honest action is
  RESET_EXPECTATIONS, not another round of clarification.
- When `inventory_stats.matching_is_meaningful` is false, ignore the match
  percentages entirely - they were computed against requirements too loose to
  mean anything.
- Do not escalate on completeness alone. A fully described buyer with no urgency
  and no financing movement is a NURTURE_LEAD, and the timeline must appear in
  your reasoning when it drives the call.

Also produce:
- `intent_score` 0-100: your own judgement of buyer intent. Start from the
  heuristic score but move it when the context justifies it, and explain any
  material difference in `reasoning`.
- `intent_tier`: HIGH / MEDIUM / LOW / NEEDS_CLARIFICATION.
- `reasoning`: 2-5 short, concrete bullets citing actual evidence (numbers,
  areas, timelines, property ids). No generic filler.
- `risks`: what could make this judgement wrong.
- `recommended_next_step`: one sentence, addressed to the brokerage team.
- `summary_headline`: under 15 words, the lead in one line.
- `draft_message`: the message this action implies, fully written and ready for
  a human to review. Audience BROKER for escalations, BUYER otherwise. This
  application never sends anything - it only displays the draft - so write it as
  a finished draft. Use null only for LOW_PRIORITY_OR_DISCARD.

This is buyer-intent and lead-quality assessment. It is not identity
verification and must never be described as such.

Return only the JSON object.
"""


# --------------------------------------------------------------------------- #
# Stage 1: understanding / merge
# --------------------------------------------------------------------------- #
def _merge_preserving(previous: LeadRequirements, incoming: LeadRequirements) -> LeadRequirements:
    """Safety net so no context is lost even if the model forgets a field.

    The model is asked to return the complete merged state. Where it returned
    nothing for a field we already knew, the known value wins.
    """
    merged = incoming.model_dump()
    old = previous.model_dump()
    for key, new_value in list(merged.items()):
        old_value = old.get(key)
        empty_new = new_value in (None, "", [], "UNKNOWN")
        if empty_new and old_value not in (None, "", [], "UNKNOWN"):
            merged[key] = old_value
    # Notes accumulate rather than replace.
    combined_notes = list(dict.fromkeys([*old.get("notes", []), *incoming.notes]))
    merged["notes"] = combined_notes[:10]
    merged["original_inquiry"] = old.get("original_inquiry") or incoming.original_inquiry
    return LeadRequirements(**merged)


def extract_requirements(
    message: str,
    previous: Optional[LeadRequirements],
    history: List[Dict[str, Any]],
    provider: LLMProvider,
) -> LeadRequirements:
    import config

    previous = previous or LeadRequirements()
    transcript = _format_history(history)
    user = (
        f"Known requirements so far (JSON):\n{previous.model_dump_json(indent=2)}\n\n"
        f"Conversation so far:\n{transcript or '(this is the first message)'}\n\n"
        f"Newest buyer message:\n\"\"\"{message}\"\"\"\n\n"
        "Return the complete merged requirements as JSON."
    )
    raw = provider.complete_json(
        system=EXTRACTION_SYSTEM.format(areas=", ".join(config.KNOWN_LOCATIONS)),
        user=user,
        schema=EXTRACTION_SCHEMA,
        max_tokens=2000,
        effort="low",
    )
    try:
        incoming = LeadRequirements(**raw)
    except Exception as exc:
        raise LLMCallError(f"Extraction output failed validation: {exc}") from exc
    incoming.original_inquiry = previous.original_inquiry or message
    return _merge_preserving(previous, incoming)


# --------------------------------------------------------------------------- #
# Stage 2: qualification + next-action reasoning
# --------------------------------------------------------------------------- #
def _compact_matches(matches: List[PropertyMatch]) -> List[Dict[str, Any]]:
    return [
        {
            "property_id": m.property_id,
            "name": m.name,
            "location": m.location,
            "type": m.property_type,
            "bhk": m.bhk,
            "price": money(m.price),
            "sqft": m.sqft,
            "match_pct": m.match_pct,
            "why": m.reasons,
            "gaps": m.gaps,
            "tags": m.tags,
        }
        for m in matches
    ]


def _format_history(history: List[Dict[str, Any]]) -> str:
    lines = []
    for turn in history[-10:]:
        role = "Buyer" if turn.get("role") == "buyer" else "Agent"
        lines.append(f"{role}: {turn.get('message', '')}")
    return "\n".join(lines)


def situation_brief(
    req: LeadRequirements, evidence: EvidencePack, matches: List[PropertyMatch]
) -> str:
    """A plain-English digest of the decision-relevant facts.

    The full JSON follows it, but models weigh a short brief far more reliably
    than a nested structure, and a human reading the audit trail can check the
    agent was told the truth.
    """
    lines = [
        f"- Budget: {req.budget_label()}",
        f"- Preferred areas: {', '.join(req.locations) or 'none stated'}",
        f"- Requirement: {req.bhk or 'unspecified'} BHK {req.property_type or 'property'}",
        f"- Timeline: {req.timeline_label()}",
        f"- Financing: {req.financing_readiness.value.replace('_', ' ').lower()}",
        f"- Missing critical information: "
        f"{', '.join(evidence.missing_critical_fields) or 'none - the buyer has covered all three'}",
        f"- Budget realism: {evidence.budget_realism.get('verdict')}"
        + (f" ({evidence.budget_realism.get('reason')})"
           if evidence.budget_realism.get("reason") else ""),
        f"- Strong inventory matches: {evidence.strong_match_count} "
        f"(top match {evidence.top_match_pct}%)",
        f"- Heuristic rubric score: {evidence.heuristic_score}/100 (evidence only)",
        f"- Conversation turns so far: {evidence.conversation_turns}",
    ]
    if not evidence.inventory_stats.get("matching_is_meaningful", True):
        lines.append("- WARNING: requirements are too loose for match percentages to mean anything.")
    if evidence.contradictions:
        lines.append("- Contradictions: " + "; ".join(evidence.contradictions))
    if not matches:
        lines.append("- No property in the inventory currently fits these requirements.")
    return "\n".join(lines)


def reason_next_action(
    req: LeadRequirements,
    evidence: EvidencePack,
    matches: List[PropertyMatch],
    history: List[Dict[str, Any]],
    provider: LLMProvider,
) -> AgentDecision:
    user = (
        f"SITUATION BRIEF:\n{situation_brief(req, evidence, matches)}\n\n"
        f"BUYER REQUIREMENTS (merged):\n{req.model_dump_json(indent=2)}\n\n"
        f"DETERMINISTIC EVIDENCE:\n{evidence.model_dump_json(indent=2)}\n\n"
        f"TOP INVENTORY MATCHES:\n{json.dumps(_compact_matches(matches), indent=2)}\n\n"
        f"CONVERSATION:\n{_format_history(history) or '(first contact)'}\n\n"
        "Decide the next business action and explain your reasoning."
    )
    raw = provider.complete_json(
        system=DECISION_SYSTEM, user=user, schema=DECISION_SCHEMA,
        max_tokens=3000, effort="medium",
    )
    try:
        return AgentDecision(**raw)
    except Exception as first_error:
        # One structured retry with the validation error fed back. If the model
        # still cannot produce a valid decision we fail loudly rather than
        # inventing one.
        retry_user = (
            user
            + f"\n\nYour previous response was rejected by validation: {first_error}\n"
            "Return a corrected JSON object that satisfies the schema exactly."
        )
        raw = provider.complete_json(
            system=DECISION_SYSTEM, user=retry_user, schema=DECISION_SCHEMA,
            max_tokens=3000, effort="medium",
        )
        try:
            return AgentDecision(**raw)
        except Exception as exc:
            raise LLMCallError(f"Decision output failed validation twice: {exc}") from exc


# --------------------------------------------------------------------------- #
# Structured lead summary
# --------------------------------------------------------------------------- #
def build_summary(
    lead_id: str,
    req: LeadRequirements,
    decision: AgentDecision,
    matches: List[PropertyMatch],
    evidence: EvidencePack,
) -> Dict[str, Any]:
    return {
        "lead_id": lead_id,
        "name": req.name or "Unnamed buyer",
        "contact": req.contact,
        "budget": req.budget_label(),
        "locations": req.locations or [],
        "property": " ".join(
            part for part in [
                f"{req.bhk} BHK" if req.bhk else "",
                req.property_type or "",
            ] if part
        ) or "Not specified",
        "timeline": req.timeline_label(),
        "financing": req.financing_method or req.financing_readiness.value.replace("_", " ").title(),
        "intent": decision.intent_tier.value,
        "intent_score": decision.intent_score,
        "top_matches": [m.property_id for m in matches[:3]],
        "decision": decision.decision.value,
        "reason": decision.reasoning[0] if decision.reasoning else "",
        "reasoning": decision.reasoning,
        "recommended_next_step": decision.recommended_next_step,
        "headline": decision.summary_headline,
        "heuristic_score": evidence.heuristic_score,
        "generated_at": utc_now(),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_turn(
    message: str,
    lead_id: Optional[str] = None,
    name: Optional[str] = None,
    contact: Optional[str] = None,
    provider: Optional[LLMProvider] = None,
) -> TurnResult:
    """Run one full agent turn and persist everything it produced."""
    message = (message or "").strip()
    if not message:
        raise ValueError("An inquiry message is required.")

    provider = provider or llm_service.get_provider()

    # --- load or create the lead -------------------------------------------
    created_here = lead_id is None
    if lead_id:
        lead = db.get_lead(lead_id)
        if lead is None:
            raise ValueError(f"Unknown lead_id {lead_id!r}")
    else:
        lead_id = db.create_lead(name=name, contact=contact, original_inquiry=message)
        lead = db.get_lead(lead_id)

    try:
        return _run_turn_inner(message, lead_id, lead, name, contact, provider)
    except Exception:
        # A turn that never reached a decision must not leave a half-formed lead
        # sitting in the dashboard. Only roll back a lead this call created;
        # an existing lead keeps its history untouched.
        if created_here:
            db.delete_lead(lead_id)
        raise


def _run_turn_inner(
    message: str,
    lead_id: str,
    lead: Dict[str, Any],
    name: Optional[str],
    contact: Optional[str],
    provider: LLMProvider,
) -> TurnResult:
    warnings: List[str] = []

    previous_raw = dict(lead.get("requirements") or {})
    previous = LeadRequirements(**previous_raw) if previous_raw else LeadRequirements()
    if name and not previous.name:
        previous.name = name
    if contact and not previous.contact:
        previous.contact = contact
    status_before = lead.get("status") or LeadStatus.NEW.value

    history = db.get_turns(lead_id)
    db.add_turn(lead_id, "buyer", message)

    # --- stage 1: understanding --------------------------------------------
    req = extract_requirements(message, previous, history, provider)
    if name:
        req.name = name
    if contact:
        req.contact = contact
    if not req.original_inquiry:
        req.original_inquiry = lead.get("original_inquiry") or message

    # --- deterministic middle ----------------------------------------------
    properties = db.list_properties()
    matches = matcher.match_properties(req, properties, limit=5)
    turn_count = db.buyer_turn_count(lead_id)
    evidence = signals.compute_evidence(
        req, matches, properties,
        previous_requirements=previous_raw or None,
        conversation_turns=turn_count,
    )

    # --- stage 2: judgement -------------------------------------------------
    decision = reason_next_action(req, evidence, matches, history + [
        {"role": "buyer", "message": message}
    ], provider)

    if abs(decision.intent_score - evidence.heuristic_score) >= 25:
        warnings.append(
            f"Agent score ({decision.intent_score}) diverges sharply from the heuristic "
            f"rubric ({evidence.heuristic_score}); check the reasoning."
        )

    # --- persist -------------------------------------------------------------
    status_after = decision.status
    summary = build_summary(lead_id, req, decision, matches, evidence)

    agent_reply = decision.follow_up_question or decision.recommended_next_step
    db.add_turn(lead_id, "agent", agent_reply)

    db.update_lead(
        lead_id,
        name=req.name,
        contact=req.contact,
        requirements=req.model_dump(mode="json"),
        intent_score=decision.intent_score,
        intent_tier=decision.intent_tier.value,
        status=status_after,
        current_action=decision.decision.value,
        recommended_next_step=decision.recommended_next_step,
        summary=summary,
    )

    db.record_action(
        lead_id=lead_id,
        decision=decision.decision.value,
        intent_score=decision.intent_score,
        intent_tier=decision.intent_tier.value,
        reasoning=decision.reasoning,
        input_snapshot={
            "buyer_message": message,
            "requirements_before": previous_raw,
            "requirements_after": req.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "matches": [m.property_id for m in matches],
        },
        output_snapshot=decision.model_dump(mode="json"),
        status_before=status_before,
        status_after=status_after,
        llm_provider=provider.label(),
    )

    return TurnResult(
        lead_id=lead_id,
        requirements=req,
        evidence=evidence,
        matches=matches,
        decision=decision,
        status=status_after,
        previous_status=status_before,
        previous_tier=lead.get("intent_tier"),
        llm_provider=provider.label(),
        warnings=warnings,
    )


__all__ = [
    "run_turn",
    "extract_requirements",
    "reason_next_action",
    "build_summary",
    "EXTRACTION_SCHEMA",
    "DECISION_SCHEMA",
    "LLMUnavailable",
    "LLMCallError",
]
