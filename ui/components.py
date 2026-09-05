"""Shared Streamlit rendering helpers.

Deliberately light on styling: the brief asks for a clean functional UI, not a
design exercise. Everything here is presentation only - no business logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from models.schemas import (
    AgentDecision,
    EvidencePack,
    LeadRequirements,
    PropertyMatch,
    money,
)
from services import drafts

TIER_COLOURS = {
    "HIGH": "#1a7f37",
    "MEDIUM": "#9a6700",
    "LOW": "#6e7781",
    "NEEDS_CLARIFICATION": "#0969da",
}

ACTION_LABELS = {
    "ASK_MORE_INFO": "Ask for more information",
    "SHOW_MATCHING_PROPERTIES": "Share matching properties",
    "ESCALATE_TO_BROKER": "Escalate to broker",
    "NURTURE_LEAD": "Nurture lead",
    "RESET_EXPECTATIONS": "Reset expectations",
    "LOW_PRIORITY_OR_DISCARD": "Deprioritise",
}

STATUS_ORDER = [
    "NEW", "NEEDS_INFORMATION", "QUALIFYING", "QUALIFIED",
    "NURTURING", "BROKER_ESCALATION", "LOW_PRIORITY",
]


def tier_badge(tier: str, score: Optional[int] = None) -> str:
    colour = TIER_COLOURS.get(tier, "#6e7781")
    label = tier.replace("_", " ").title()
    suffix = f" &nbsp;{score}/100" if score is not None else ""
    return (
        f"<span style='background:{colour};color:#fff;padding:3px 10px;"
        f"border-radius:12px;font-size:0.85rem;font-weight:600'>{label}{suffix}</span>"
    )


def render_intent_header(decision: AgentDecision, evidence: EvidencePack) -> None:
    left, mid, right = st.columns([2, 1, 1])
    with left:
        st.markdown("**Buyer intent**", help="Lead-quality assessment, not identity verification.")
        st.markdown(tier_badge(decision.intent_tier.value, decision.intent_score),
                    unsafe_allow_html=True)
    with mid:
        st.metric("Heuristic rubric", f"{evidence.heuristic_score}/100",
                  help="Deterministic evidence score given to the agent. Not the decision.")
    with right:
        st.metric("Information completeness", f"{evidence.completeness_pct}%")


def render_next_action(decision: AgentDecision) -> None:
    label = ACTION_LABELS.get(decision.decision.value, decision.decision.value)
    st.subheader(f"Next action: {label}")
    st.caption(f"`{decision.decision.value}`  ·  agent confidence {decision.confidence:.0%}")
    if decision.summary_headline:
        st.write(f"**{decision.summary_headline}**")


def render_requirements(req: LeadRequirements) -> None:
    rows = [
        ("Name", req.name or "-"),
        ("Contact", req.contact or "-"),
        ("Budget", req.budget_label()),
        ("Locations", ", ".join(req.locations) or "-"),
        ("Property", " ".join(p for p in [f"{req.bhk} BHK" if req.bhk else "",
                                          req.property_type or ""] if p) or "-"),
        ("Minimum sqft", str(req.min_sqft) if req.min_sqft else "-"),
        ("Timeline", req.timeline_label()),
        ("Financing", req.financing_method or "-"),
        ("Financing readiness", req.financing_readiness.value.replace("_", " ").title()),
        ("Amenities", ", ".join(req.amenities) or "-"),
        ("Parking", {True: "Required", False: "Not required", None: "-"}[req.parking_required]),
        ("Furnishing", req.furnishing or "-"),
        ("Purpose", req.purpose.value.replace("_", " ").title()),
        ("Viewing ready", {True: "Yes", False: "No", None: "-"}[req.viewing_ready]),
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Field", "Value"]),
        hide_index=True, width="stretch",
    )
    if req.notes:
        st.caption("Agent notes: " + " · ".join(req.notes))


def render_reasoning(decision: AgentDecision) -> None:
    st.markdown("**Agent reasoning**")
    for line in decision.reasoning:
        st.markdown(f"- {line}")
    if decision.missing_information:
        st.markdown("**Still missing**")
        for line in decision.missing_information:
            st.markdown(f"- {line}")
    if decision.risks:
        st.markdown("**Risks / uncertainty**")
        for line in decision.risks:
            st.markdown(f"- {line}")


def render_evidence(evidence: EvidencePack) -> None:
    with st.expander("Deterministic evidence given to the agent", expanded=False):
        st.caption(
            "Computed in Python, not by the model. The agent weighs this alongside "
            "the conversation; it does not select the action by threshold."
        )
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Score rubric**")
            breakdown = pd.DataFrame(
                sorted(evidence.score_breakdown.items(), key=lambda kv: -kv[1]),
                columns=["Component", "Points"],
            )
            st.dataframe(breakdown, hide_index=True, width="stretch")
        with col2:
            st.markdown("**Budget realism**")
            st.json(evidence.budget_realism, expanded=True)
        st.markdown("**Inventory reality check**")
        st.json(evidence.inventory_stats, expanded=False)
        if evidence.contradictions:
            st.markdown("**Contradictions across turns**")
            for note in evidence.contradictions:
                st.markdown(f"- {note}")


def matches_dataframe(matches: List[PropertyMatch]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": m.property_id,
                "Property": m.name,
                "Area": m.location,
                "Type": m.property_type,
                "BHK": m.bhk if m.bhk is not None else "-",
                "Sqft": m.sqft,
                "Price": money(m.price),
                "Match %": m.match_pct,
                "Why it matches": "; ".join(m.reasons) or "-",
                "Gaps": "; ".join(m.gaps) or "-",
            }
            for m in matches
        ]
    )


def render_matches(matches: List[PropertyMatch], meaningful: bool = True) -> None:
    st.markdown("**Top property matches**")
    if not matches:
        st.info("No property in the current inventory matches these requirements.")
        return
    if not meaningful:
        st.warning(
            "Requirements are still too loose for matching to be informative - these "
            "percentages should not be read as evidence of fit."
        )
    st.dataframe(
        matches_dataframe(matches),
        hide_index=True,
        width="stretch",
        column_config={
            "Match %": st.column_config.ProgressColumn(
                "Match %", min_value=0, max_value=100, format="%d%%"
            )
        },
    )


def render_draft(lead_id: str, req: LeadRequirements, decision: AgentDecision,
                 matches: List[PropertyMatch]) -> None:
    st.markdown("**Recommended business action**")
    st.success(decision.recommended_next_step)
    draft = drafts.resolve_draft(lead_id, req, decision, matches)
    if draft is None:
        st.caption("This action implies no outgoing message.")
        return
    st.markdown("**Generated draft** (displayed only - this app sends nothing)")
    st.code(drafts.render_draft(draft), language="text")


def render_summary(summary: Dict[str, Any]) -> None:
    if not summary:
        st.caption("No structured summary stored yet.")
        return
    st.code(
        "\n".join(
            [
                f"Lead ID:        {summary.get('lead_id', '-')}",
                f"Name:           {summary.get('name', '-')}",
                f"Budget:         {summary.get('budget', '-')}",
                f"Locations:      {', '.join(summary.get('locations') or []) or '-'}",
                f"Property:       {summary.get('property', '-')}",
                f"Timeline:       {summary.get('timeline', '-')}",
                f"Financing:      {summary.get('financing', '-')}",
                f"Intent:         {summary.get('intent', '-')} ({summary.get('intent_score', '-')}/100)",
                f"Top matches:    {', '.join(summary.get('top_matches') or []) or 'none'}",
                f"Decision:       {summary.get('decision', '-')}",
                f"Reason:         {summary.get('reason', '-')}",
                f"Next step:      {summary.get('recommended_next_step', '-')}",
            ]
        ),
        language="text",
    )


def render_status_transition(before: Optional[str], after: str) -> None:
    if before and before != after:
        st.info(f"Database updated: lead status **{before} → {after}**")
    else:
        st.caption(f"Lead status unchanged: **{after}**")


def render_conversation(turns: List[Dict[str, Any]]) -> None:
    if not turns:
        st.caption("No conversation recorded yet.")
        return
    for turn in turns:
        role = "user" if turn.get("role") == "buyer" else "assistant"
        with st.chat_message(role):
            st.write(turn.get("message", ""))


def render_decision_history(actions: List[Dict[str, Any]]) -> None:
    if not actions:
        st.caption("No decisions recorded yet.")
        return
    for action in actions:
        header = (
            f"{action['timestamp']} · {ACTION_LABELS.get(action['decision'], action['decision'])} "
            f"· {action.get('intent_tier', '-')} {action.get('intent_score', '-')}/100"
        )
        with st.expander(header):
            st.markdown(
                f"Status: **{action.get('status_before') or '-'} → {action.get('status_after')}**  ·  "
                f"model: `{action.get('llm_provider') or 'n/a'}`"
            )
            for line in action.get("reasoning") or []:
                st.markdown(f"- {line}")
            cols = st.columns(2)
            with cols[0]:
                st.caption("Input snapshot")
                st.json(action.get("input_snapshot") or {}, expanded=False)
            with cols[1]:
                st.caption("Output snapshot")
                st.json(action.get("output_snapshot") or {}, expanded=False)
