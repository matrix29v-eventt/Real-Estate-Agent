"""Streamlit entry point for the Real Estate Lead Qualification Agent.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

import config
from services import db, llm_service
from ui import analysis, dashboard, new_lead

st.set_page_config(page_title=config.APP_TITLE, page_icon="RE", layout="wide")

VIEWS = ["New Lead / Conversation", "Lead Analysis", "Lead Dashboard"]


@st.cache_resource
def _bootstrap() -> dict:
    """Create and seed the database once per server process."""
    return db.ensure_seeded()


def _sidebar() -> None:
    with st.sidebar:
        st.markdown("### Agent status")
        status = llm_service.provider_status()
        if status["configured"]:
            active = status["active"]
            st.success(f"LLM ready: `{active['provider']}` / `{active['model']}`")
        else:
            st.error("No LLM configured — the agent cannot reason.")
            st.caption(
                "Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` "
                "(or run a local Ollama model and set `LLM_PROVIDER=ollama`). "
                "This app never fabricates an analysis when no model is reachable."
            )
        with st.expander("Provider detail", expanded=not status["configured"]):
            for entry in status["providers"]:
                icon = "OK  " if entry["usable"] else "--  "
                st.caption(f"{icon}**{entry['provider']}** ({entry['model']}): {entry['detail']}")

        st.markdown("### Data")
        st.caption(f"Database: `{config.db_path().name}`")
        counts = st.columns(2)
        counts[0].metric("Properties", db.count_rows("properties"))
        counts[1].metric("Leads", db.count_rows("leads"))

        if st.button("Reset demo data", width="stretch"):
            db.reset_db()
            db.ensure_seeded(force=True)
            _bootstrap.clear()
            for key in ("active_lead_id", "last_result", "agent_error"):
                st.session_state[key] = None
            st.rerun()

        st.markdown("---")
        st.caption(
            "**Buyer intent** here means lead quality and purchase readiness. "
            "It is not identity or KYC verification."
        )
        st.caption(
            "No message is ever sent externally. Broker escalations and buyer "
            "replies are rendered as drafts inside the app."
        )


def main() -> None:
    _bootstrap()
    st.title(config.APP_TITLE)
    st.caption(
        "Which inquiries deserve a broker's immediate attention, which need more "
        "qualification, and which should be deprioritised?"
    )
    _sidebar()

    for key, default in (
        ("active_lead_id", None),
        ("last_result", None),
        ("agent_error", None),
        ("inquiry_text", ""),
        ("followup_text", ""),
        ("active_view", VIEWS[0]),
    ):
        st.session_state.setdefault(key, default)

    # st.tabs resets to the first tab on every rerun, which would strand anyone
    # who navigates here from the dashboard. A keyed selector survives reruns.
    pending = st.session_state.pop("pending_view", None)
    if pending in VIEWS:
        st.session_state["active_view"] = pending

    view = st.radio(
        "View", VIEWS, key="active_view", horizontal=True, label_visibility="collapsed"
    )
    st.divider()

    if view == VIEWS[0]:
        new_lead.render()
    elif view == VIEWS[1]:
        analysis.render()
    else:
        dashboard.render()


if __name__ == "__main__":
    main()
