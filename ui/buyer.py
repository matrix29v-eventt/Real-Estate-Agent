"""The buyer-facing portal.

A buyer sees their own enquiry, the properties the agent matched, and where
their enquiry stands. They deliberately do **not** see broker-facing internals:
the intent score, the heuristic rubric, the escalation decision or the drafted
broker message. Showing a buyer that they scored 22/100 and were deprioritised
would be a poor experience and is not information they are owed.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from models.schemas import LeadRequirements, NextAction
from services import agent, auth, db
from services.llm_service import LLMCallError, LLMUnavailable
from ui import components
from ui.analysis import rebuild_from_db

BUYER_SECTIONS = ["New enquiry", "My enquiries"]

# What the buyer is told, per decision. The agent's internal action name is
# never shown to them.
BUYER_STATUS = {
    NextAction.ASK_MORE_INFO.value: (
        "A few more details needed",
        "Answer the question below and we will refine your matches.",
    ),
    NextAction.SHOW_MATCHING_PROPERTIES.value: (
        "Matches found",
        "Here are the properties that best fit what you described.",
    ),
    NextAction.ESCALATE_TO_BROKER.value: (
        "Passed to an agent",
        "One of our property advisors will contact you shortly to arrange viewings.",
    ),
    NextAction.NURTURE_LEAD.value: (
        "Saved for later",
        "We will keep you posted as new listings arrive. Tell us if your plans change.",
    ),
    NextAction.RESET_EXPECTATIONS.value: (
        "Let's adjust the search",
        "Nothing currently on the market fits that combination. See the note below.",
    ),
    NextAction.LOW_PRIORITY_OR_DISCARD.value: (
        "Enquiry received",
        "Send us more detail whenever you are ready and we will pick this up.",
    ),
}


def _process(message: str, lead_id: Optional[str], account: auth.Account) -> None:
    import time

    started = time.monotonic()
    status = st.status("Sending your enquiry to our property agent...", expanded=True)

    def on_stage(label: str) -> None:
        status.update(label=f"{label}  ({time.monotonic() - started:.0f}s)")
        status.write(label)

    with status:
        try:
            result = agent.run_turn(
                message,
                lead_id=lead_id,
                name=account.display_name,
                contact=st.session_state.get("buyer_contact_value") or None,
                on_stage=on_stage,
                owner=account.username,
            )
        except LLMUnavailable as exc:
            status.update(label="Agent unavailable", state="error")
            st.session_state["agent_error"] = (
                "Our property agent is not available right now, so your enquiry "
                f"was not analysed.\n\n{exc}"
            )
            return
        except LLMCallError as exc:
            status.update(label="Agent could not respond", state="error")
            st.session_state["agent_error"] = (
                f"Something went wrong while analysing your enquiry: {exc}"
            )
            return
        except ValueError as exc:
            status.update(label="Could not send that", state="error")
            st.session_state["agent_error"] = str(exc)
            return

    status.update(label="Enquiry analysed", state="complete")
    st.session_state["agent_error"] = None
    st.session_state["active_lead_id"] = result.lead_id
    st.session_state["last_result"] = result
    st.session_state["clear_buyer_inputs"] = True


def _render_new_enquiry(account: auth.Account) -> None:
    st.subheader("Tell us what you are looking for")
    st.caption(
        "Describe it in your own words — budget, area, size, when you hope to buy "
        "and anything else that matters to you."
    )

    st.text_input(
        "Contact (optional)",
        key="buyer_contact_value",
        placeholder="Phone or email, if you would like us to get in touch",
    )
    st.text_area(
        "Your enquiry",
        key="buyer_inquiry_text",
        height=130,
        placeholder="e.g. Looking for a 3BHK near Technopark, budget around 70 lakh, "
                    "hoping to buy within 2 months. Need parking.",
    )

    if st.button("Send enquiry", type="primary", width="stretch"):
        message = st.session_state.get("buyer_inquiry_text", "").strip()
        if not message:
            st.session_state["agent_error"] = "Please describe what you are looking for."
        else:
            _process(message, lead_id=None, account=account)
        st.rerun()

    if st.session_state.get("agent_error"):
        st.error(st.session_state["agent_error"])


def _render_active_enquiry(account: auth.Account) -> None:
    lead_id = st.session_state.get("active_lead_id")
    if not lead_id:
        return
    lead = db.get_lead(lead_id)
    if not lead or lead.get("owner") != account.username:
        return

    result = st.session_state.get("last_result")
    if result is None or result.lead_id != lead_id:
        result = rebuild_from_db(lead_id)
    if result is None:
        return

    st.divider()
    headline, blurb = BUYER_STATUS.get(
        result.decision.decision.value, ("Enquiry received", "")
    )
    st.subheader(headline)
    if blurb:
        st.write(blurb)

    st.markdown("**Your conversation**")
    components.render_conversation(db.get_turns(lead_id))

    if result.decision.follow_up_question:
        st.info(result.decision.follow_up_question)

    st.text_area(
        "Your reply",
        key="buyer_followup_text",
        height=90,
        placeholder="Type your answer here...",
    )
    if st.button("Send reply", width="stretch"):
        reply = st.session_state.get("buyer_followup_text", "").strip()
        if not reply:
            st.session_state["agent_error"] = "Please type a reply before sending."
        else:
            _process(reply, lead_id=lead_id, account=account)
        st.rerun()

    if result.decision.decision == NextAction.RESET_EXPECTATIONS:
        realism = result.evidence.budget_realism
        if realism.get("reason"):
            st.warning(realism["reason"])

    st.divider()
    meaningful = bool(result.evidence.inventory_stats.get("matching_is_meaningful", True))
    if meaningful and result.matches:
        components.render_matches(result.matches, meaningful=True)
    elif not meaningful:
        st.caption(
            "Tell us your budget, preferred areas and timeline and we can show you "
            "properties that genuinely fit."
        )
    else:
        st.info("Nothing in our current listings matches that yet.")

    with st.expander("What we understood from you", expanded=False):
        components.render_requirements(result.requirements)


def _render_my_enquiries(account: auth.Account) -> None:
    leads = db.list_leads(owner=account.username)
    st.subheader("My enquiries")
    if not leads:
        st.info("You have not sent an enquiry yet. Start one on the **New enquiry** tab.")
        return

    for lead in leads:
        try:
            req = LeadRequirements(**(lead.get("requirements") or {}))
        except Exception:
            req = LeadRequirements()
        headline, _ = BUYER_STATUS.get(
            lead.get("current_action") or "", ("Enquiry received", "")
        )
        label = (
            f"{lead['lead_id']} · {req.budget_label()} · "
            f"{', '.join(req.locations) or 'area not set'} · {headline}"
        )
        with st.expander(label, expanded=False):
            st.caption(f"Last updated {(lead.get('updated_at') or '')[:16].replace('T', ' ')}")
            st.write(lead.get("original_inquiry") or "")
            components.render_requirements(req)
            if st.button("Open this enquiry", key=f"open_{lead['lead_id']}"):
                st.session_state["active_lead_id"] = lead["lead_id"]
                st.session_state["last_result"] = None
                # buyer_view is the radio's key and the radio already exists on
                # this run, so it cannot be written here. Hand the change to the
                # next run instead.
                st.session_state["pending_buyer_view"] = BUYER_SECTIONS[0]
                st.rerun()


def render(account: auth.Account) -> None:
    # Clear widget values before their widgets are created this run.
    if st.session_state.pop("clear_buyer_inputs", False):
        st.session_state["buyer_inquiry_text"] = ""
        st.session_state["buyer_followup_text"] = ""

    st.session_state.setdefault("buyer_view", BUYER_SECTIONS[0])
    pending = st.session_state.pop("pending_buyer_view", None)
    if pending in BUYER_SECTIONS:
        st.session_state["buyer_view"] = pending

    view = st.radio(
        "Section", BUYER_SECTIONS, key="buyer_view",
        horizontal=True, label_visibility="collapsed",
    )
    st.divider()

    if view == BUYER_SECTIONS[0]:
        _render_new_enquiry(account)
        _render_active_enquiry(account)
    else:
        _render_my_enquiries(account)
