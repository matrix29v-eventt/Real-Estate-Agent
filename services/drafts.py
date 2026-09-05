"""Rendering of the messages an action implies.

Nothing here contacts anybody. The application has no email, SMS or messaging
integration by design: every notification, broker escalation and buyer reply is
produced as a **draft displayed in the UI** for a human to review and send
themselves.

The agent normally writes the draft itself as part of its decision. This module
formats it for display and provides a deterministic fallback so the UI always
has something coherent to show.
"""

from __future__ import annotations

from typing import List

from models.schemas import (
    AgentDecision,
    DraftMessage,
    LeadRequirements,
    NextAction,
    PropertyMatch,
    money,
)

DISCLAIMER = "DRAFT ONLY - this application does not send messages. Review and send manually."

_AUDIENCE_BY_ACTION = {
    NextAction.ESCALATE_TO_BROKER: "BROKER",
    NextAction.ASK_MORE_INFO: "BUYER",
    NextAction.SHOW_MATCHING_PROPERTIES: "BUYER",
    NextAction.NURTURE_LEAD: "BUYER",
    NextAction.RESET_EXPECTATIONS: "BUYER",
}


def _match_lines(matches: List[PropertyMatch], limit: int = 3) -> str:
    if not matches:
        return "  (no inventory currently matches these requirements)"
    return "\n".join(
        f"  - {m.name} ({m.property_id}), {m.location} | "
        f"{str(m.bhk) + ' BHK, ' if m.bhk else ''}{m.sqft} sqft | "
        f"{money(m.price)} | {m.match_pct}% match"
        for m in matches[:limit]
    )


def fallback_draft(
    lead_id: str,
    req: LeadRequirements,
    decision: AgentDecision,
    matches: List[PropertyMatch],
) -> DraftMessage:
    """Deterministic draft used only when the agent did not supply one."""
    audience = _AUDIENCE_BY_ACTION.get(decision.decision, "BUYER")
    buyer = req.name or "there"

    if audience == "BROKER":
        subject = f"[Priority lead {lead_id}] {req.name or 'Buyer'} - {req.budget_label()}"
        body = (
            f"Lead: {lead_id} ({req.name or 'name not given'})\n"
            f"Contact: {req.contact or 'not captured yet'}\n\n"
            f"Requirement: {req.bhk or '-'} BHK {req.property_type or 'property'} in "
            f"{', '.join(req.locations) or 'unspecified area'}\n"
            f"Budget: {req.budget_label()}\n"
            f"Timeline: {req.timeline_label()}\n"
            f"Financing: {req.financing_readiness.value.replace('_', ' ').title()}\n\n"
            f"Buyer intent: {decision.intent_tier.value} ({decision.intent_score}/100)\n\n"
            "Why this is being escalated:\n"
            + "\n".join(f"  - {r}" for r in decision.reasoning)
            + "\n\nSuggested properties to lead with:\n"
            + _match_lines(matches)
            + f"\n\nRecommended next step: {decision.recommended_next_step}\n"
        )
    else:
        if decision.decision == NextAction.ASK_MORE_INFO and decision.follow_up_question:
            core = decision.follow_up_question
        elif decision.decision == NextAction.RESET_EXPECTATIONS:
            core = (
                "Based on current listings, the requirements you described start at a higher "
                "price point than the budget you mentioned. Happy to show you the closest "
                "options, or nearby areas where your budget goes further."
            )
        elif decision.decision == NextAction.SHOW_MATCHING_PROPERTIES:
            core = "Here are the properties that best fit what you described:\n" + _match_lines(matches)
        else:
            core = decision.recommended_next_step

        subject = f"Your property search in Thiruvananthapuram ({lead_id})"
        body = f"Hi {buyer},\n\nThanks for getting in touch.\n\n{core}\n\nBest regards,\nSales Desk\n"

    return DraftMessage(
        audience=audience,
        channel="Email (draft only - nothing is sent)",
        subject=subject,
        body=body,
    )


def resolve_draft(
    lead_id: str,
    req: LeadRequirements,
    decision: AgentDecision,
    matches: List[PropertyMatch],
) -> DraftMessage | None:
    """Return the draft to display, or None when the action implies no message."""
    if decision.decision == NextAction.LOW_PRIORITY_OR_DISCARD and not decision.draft_message:
        return None
    if decision.draft_message and decision.draft_message.body.strip():
        draft = decision.draft_message
        if not draft.channel:
            draft.channel = "Email (draft only - nothing is sent)"
        return draft
    return fallback_draft(lead_id, req, decision, matches)


def render_draft(draft: DraftMessage) -> str:
    """Plain-text rendering for display inside the app."""
    audience = "Broker / internal" if draft.audience == "BROKER" else "Buyer"
    return (
        f"To: {audience}\n"
        f"Channel: {draft.channel}\n"
        f"Subject: {draft.subject}\n"
        f"{'-' * 60}\n"
        f"{draft.body.rstrip()}\n"
        f"{'-' * 60}\n"
        f"{DISCLAIMER}"
    )
