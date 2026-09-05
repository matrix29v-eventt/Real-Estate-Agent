"""Tab A - new lead intake and the agent conversation."""

from __future__ import annotations

import streamlit as st

import config
from services import agent, db
from services.llm_service import LLMCallError, LLMUnavailable
from ui import components

DEMO_SCENARIOS = {
    "1. High-intent buyer": (
        "Looking for a 3BHK apartment around Technopark or Kazhakkoottam. "
        "Budget 65-75 lakh. Planning to purchase within 2 months. Need parking and "
        "preferably a gated community. Home loan is already being processed."
    ),
    "2. Ambiguous inquiry": "I need a nice flat in Trivandrum.",
    "2b. Follow-up answer": (
        "Around 65 lakh, close to Technopark, hopefully within two months. "
        "The bank has already approved my loan."
    ),
    "3. Unrealistic requirement": (
        "I want a 4BHK premium property in Kowdiar for 25 lakh."
    ),
    "4. Long-term browser": (
        "Looking at 3BHK properties around 80 lakh but probably won't buy for "
        "another 18 months."
    ),
}


def _prefill(text: str) -> None:
    st.session_state["inquiry_text"] = text


def _process(message: str, name: str, contact: str, lead_id: str | None) -> None:
    with st.spinner("Agent is reading the inquiry, checking inventory and deciding..."):
        try:
            result = agent.run_turn(
                message,
                lead_id=lead_id,
                name=name.strip() or None,
                contact=contact.strip() or None,
            )
        except LLMUnavailable as exc:
            st.session_state["agent_error"] = (
                f"No LLM is configured, so no analysis was performed.\n\n{exc}\n\n"
                "Set ANTHROPIC_API_KEY in your .env (or run a local Ollama model) "
                "and reload. Nothing is fabricated when a model is unavailable."
            )
            return
        except LLMCallError as exc:
            hint = ""
            if "timed out" in str(exc).lower():
                hint = (
                    "\n\nThe model did not answer within "
                    f"{config.LLM_TIMEOUT_SECONDS:.0f}s. Local models on CPU are often "
                    "slower than that — raise `LLM_TIMEOUT_SECONDS` in your .env, "
                    "choose a smaller local model, or use Anthropic."
                )
            st.session_state["agent_error"] = f"The model call failed: {exc}{hint}"
            return
        except ValueError as exc:
            st.session_state["agent_error"] = str(exc)
            return

    st.session_state["agent_error"] = None
    st.session_state["active_lead_id"] = result.lead_id
    st.session_state["last_result"] = result
    st.session_state["inquiry_text"] = ""
    st.session_state["followup_text"] = ""


def render() -> None:
    st.subheader("New lead / agent conversation")
    st.caption(
        "Enter a natural-language property inquiry. The agent extracts requirements, "
        "checks live inventory, assesses buyer intent and decides the next business action."
    )

    with st.expander("Load a demo scenario", expanded=False):
        cols = st.columns(len(DEMO_SCENARIOS))
        for col, (label, text) in zip(cols, DEMO_SCENARIOS.items()):
            col.button(label, width="stretch", on_click=_prefill, args=(text,),
                       key=f"scenario_{label}")

    active_lead_id = st.session_state.get("active_lead_id")
    lead = db.get_lead(active_lead_id) if active_lead_id else None

    col_a, col_b = st.columns(2)
    default_name = (lead or {}).get("name") or ""
    default_contact = (lead or {}).get("contact") or ""
    name = col_a.text_input("Buyer name (optional)", value=default_name, key="buyer_name")
    contact = col_b.text_input("Contact (optional)", value=default_contact, key="buyer_contact")

    st.text_area(
        "Property inquiry",
        key="inquiry_text",
        height=120,
        placeholder="e.g. Looking for a 3BHK near Technopark, budget around 70 lakh, "
                    "want to buy within 2 months.",
    )

    left, right = st.columns([1, 3])
    if left.button("Analyse inquiry", type="primary", width="stretch"):
        message = st.session_state.get("inquiry_text", "").strip()
        if not message:
            st.session_state["agent_error"] = "Enter an inquiry before analysing."
        else:
            _process(message, name, contact, lead_id=None)
        st.rerun()
    if active_lead_id and right.button("Start a new lead", width="stretch"):
        st.session_state["active_lead_id"] = None
        st.session_state["last_result"] = None
        st.session_state["agent_error"] = None
        st.rerun()

    if st.session_state.get("agent_error"):
        st.error(st.session_state["agent_error"])

    result = st.session_state.get("last_result")
    if not active_lead_id or result is None:
        return

    st.divider()
    st.markdown(f"### Active lead `{active_lead_id}`")

    components.render_intent_header(result.decision, result.evidence)
    components.render_next_action(result.decision)
    components.render_status_transition(result.previous_status, result.status)

    st.markdown("**Conversation**")
    components.render_conversation(db.get_turns(active_lead_id))

    if result.decision.follow_up_question:
        st.info(f"Agent needs more context: {result.decision.follow_up_question}")

    st.markdown("**Continue the conversation** (previous context is preserved)")
    st.text_area(
        "Buyer reply",
        key="followup_text",
        height=90,
        placeholder="Answer the agent's question here...",
        label_visibility="collapsed",
    )
    if st.button("Send reply", width="stretch"):
        reply = st.session_state.get("followup_text", "").strip()
        if not reply:
            st.session_state["agent_error"] = "Enter a reply before sending."
        else:
            _process(reply, name, contact, lead_id=active_lead_id)
        st.rerun()

    with st.expander("Extracted information so far", expanded=True):
        components.render_requirements(result.requirements)

    if st.button("Open full analysis", type="primary", width="stretch"):
        st.session_state["pending_view"] = "Lead Analysis"
        st.rerun()
    st.caption("Reasoning, evidence, property matches and the generated draft "
               "are all on the Lead Analysis view.")
