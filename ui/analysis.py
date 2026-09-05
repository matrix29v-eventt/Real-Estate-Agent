"""Tab B - full analysis of the active lead."""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from models.schemas import AgentDecision, EvidencePack, LeadRequirements, TurnResult
from services import db, matcher, signals
from ui import components


def rebuild_from_db(lead_id: str) -> Optional[TurnResult]:
    """Reconstruct a viewable result for a lead analysed in an earlier session.

    Requirements and the decision come from storage; matches and evidence are
    recomputed deterministically against current inventory, which is exactly
    what makes them reproducible.
    """
    lead = db.get_lead(lead_id)
    if not lead:
        return None
    try:
        req = LeadRequirements(**(lead.get("requirements") or {}))
    except Exception:
        req = LeadRequirements()

    properties = db.list_properties()
    matches = matcher.match_properties(req, properties)
    evidence = signals.compute_evidence(
        req, matches, properties, conversation_turns=db.buyer_turn_count(lead_id)
    )

    actions = db.get_actions(lead_id)
    decision = _decision_from_action(actions[0] if actions else None, lead)
    if decision is None:
        return None

    return TurnResult(
        lead_id=lead_id,
        requirements=req,
        evidence=evidence,
        matches=matches,
        decision=decision,
        status=lead.get("status") or "NEW",
        previous_status=(actions[0].get("status_before") if actions else None),
        llm_provider=(actions[0].get("llm_provider") if actions else ""),
    )


def _decision_from_action(action: Optional[Dict[str, Any]],
                          lead: Dict[str, Any]) -> Optional[AgentDecision]:
    if action:
        snapshot = action.get("output_snapshot") or {}
        try:
            return AgentDecision(**snapshot)
        except Exception:
            pass
        try:
            return AgentDecision(
                intent_score=action.get("intent_score") or 0,
                intent_tier=action.get("intent_tier") or "LOW",
                decision=action.get("decision") or "ASK_MORE_INFO",
                reasoning=action.get("reasoning") or ["(reasoning not recorded)"],
                recommended_next_step=lead.get("recommended_next_step") or "-",
                summary_headline=(lead.get("summary") or {}).get("headline", ""),
            )
        except Exception:
            return None
    return None


def render() -> None:
    lead_id = st.session_state.get("active_lead_id")
    if not lead_id:
        st.info("Analyse an inquiry on the **New Lead** tab, or pick a lead on the "
                "**Dashboard**, to see its analysis here.")
        return

    result: Optional[TurnResult] = st.session_state.get("last_result")
    if result is None or result.lead_id != lead_id:
        result = rebuild_from_db(lead_id)
    if result is None:
        st.warning(f"Lead `{lead_id}` has no recorded agent decision yet.")
        return

    lead = db.get_lead(lead_id) or {}
    st.subheader(f"Lead `{lead_id}` — {result.requirements.name or 'Unnamed buyer'}")
    st.caption(f"Model: `{result.llm_provider or 'n/a'}` · current status **{result.status}**")

    for warning in result.warnings:
        st.warning(warning)

    components.render_intent_header(result.decision, result.evidence)
    st.divider()

    components.render_next_action(result.decision)
    components.render_status_transition(result.previous_status, result.status)
    st.divider()

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Extracted requirements**")
        components.render_requirements(result.requirements)
    with right:
        components.render_reasoning(result.decision)

    components.render_evidence(result.evidence)
    st.divider()

    components.render_matches(
        result.matches,
        meaningful=bool(result.evidence.inventory_stats.get("matching_is_meaningful", True)),
    )
    st.divider()

    components.render_draft(lead_id, result.requirements, result.decision, result.matches)
    st.divider()

    st.markdown("**Structured lead summary**")
    components.render_summary(lead.get("summary") or {})

    with st.expander("Conversation", expanded=False):
        components.render_conversation(db.get_turns(lead_id))

    with st.expander("Decision history (audit trail)", expanded=False):
        components.render_decision_history(db.get_actions(lead_id))
