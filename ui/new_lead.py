"""Tab A - new lead intake and the agent conversation."""

from __future__ import annotations

import time

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
    started = time.monotonic()
    status = st.status("Starting the agent...", expanded=True)

    def on_stage(label: str) -> None:
        # A turn makes two LLM calls. On a slow local model each can take
        # minutes, so show which stage is running and how long it has been.
        status.update(label=f"{label}  ({time.monotonic() - started:.0f}s)")
        status.write(label)

    with status:
        try:
            result = agent.run_turn(
                message,
                lead_id=lead_id,
                name=name.strip() or None,
                contact=contact.strip() or None,
                on_stage=on_stage,
            )
        except LLMUnavailable as exc:
            status.update(label="No LLM configured", state="error")
            st.session_state["agent_error"] = (
                f"No LLM is configured, so no analysis was performed.\n\n{exc}\n\n"
                "Set GEMINI_API_KEY and LLM_PROVIDER=gemini in your .env "
                "(or configure Anthropic or a local Ollama model) "
                "and reload. Nothing is fabricated when a model is unavailable."
            )
            return
        except LLMCallError as exc:
            status.update(
                label=f"Model call failed after {time.monotonic() - started:.0f}s",
                state="error",
            )
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
            status.update(label="Could not run the turn", state="error")
            st.session_state["agent_error"] = str(exc)
            return

    elapsed = time.monotonic() - started
    status.update(
        label=f"Decision: {result.decision.decision.value} ({elapsed:.0f}s)",
        state="complete",
    )
    st.session_state["agent_error"] = None
    st.session_state["last_turn_seconds"] = elapsed
    st.session_state["active_lead_id"] = result.lead_id
    st.session_state["last_result"] = result
    st.session_state["clear_lead_inputs"] = True


def render() -> None:
    # Clear widget values on the next run, before their widgets are created.
    if st.session_state.pop("clear_lead_inputs", False):
        st.session_state["inquiry_text"] = ""
        st.session_state["followup_text"] = ""

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
    header, timing = st.columns([3, 1])
    header.markdown(f"### Active lead `{active_lead_id}`")
    seconds = st.session_state.get("last_turn_seconds")
    if seconds:
        timing.caption(f"Last turn took {seconds:.0f}s "
                       f"({result.llm_provider or 'model'}, 2 calls)")

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
