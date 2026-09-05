"""Streamlit entry point for the Real Estate Lead Qualification Agent.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

import config
from services import auth, db, llm_service
from ui import analysis, buyer, dashboard, login, new_lead, properties

st.set_page_config(page_title=config.APP_TITLE, page_icon="RE", layout="wide")

BROKER_VIEWS = [
    "New Lead / Conversation",
    "Lead Analysis",
    "Lead Dashboard",
    "Property Inventory",
]

# Kept for backwards compatibility with existing tests and bookmarks.
VIEWS = BROKER_VIEWS


@st.cache_resource
def _bootstrap() -> dict:
    """Create and seed the database once per server process."""
    return db.ensure_seeded()


def _account_sidebar(account: auth.Account) -> None:
    with st.sidebar:
        st.markdown(f"### {account.role_label}")
        st.write(account.display_name)
        if st.button("Sign out", width="stretch"):
            auth.sign_out(st.session_state)
            st.rerun()
        st.markdown("---")


def _sidebar(account: auth.Account) -> None:
    with st.sidebar:
        st.markdown("### Agent status")
        status = llm_service.provider_status()
        if status["configured"]:
            active = status["active"]
            st.success(f"LLM ready: `{active['provider']}` / `{active['model']}`")
            if active["provider"] == "ollama":
                st.caption(
                    f"Local model. Each turn makes 2 calls, so a turn can take "
                    f"minutes on CPU — the timeout is "
                    f"{config.LLM_TIMEOUT_SECONDS:.0f}s per call. If turns are too "
                    f"slow, use a smaller model or configure Gemini in .env."
                )
        else:
            st.error("No LLM configured — the agent cannot reason.")
            st.caption(
                "Set `GEMINI_API_KEY` and `LLM_PROVIDER=gemini` in `.env` "
                "(or run a local Ollama model and set `LLM_PROVIDER=ollama`). "
                "This app never fabricates an analysis when no model is reachable."
            )
        with st.expander("Provider detail", expanded=not status["configured"]):
            for entry in status["providers"]:
                icon = "OK  " if entry["usable"] else "--  "
                st.caption(f"{icon}**{entry['provider']}** ({entry['model']}): {entry['detail']}")

        if not account.is_broker:
            st.markdown("---")
            st.caption(
                "**Buyer intent** assessment is lead-quality scoring, not identity "
                "or KYC verification."
            )
            return

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

    account = auth.current_account(st.session_state)
    if account is None:
        st.caption(
            "Buyers describe what they are looking for; brokers see which enquiries "
            "deserve their time."
        )
        login.render()
        return

    _account_sidebar(account)
    _sidebar(account)

    for key, default in (
        ("active_lead_id", None),
        ("last_result", None),
        ("agent_error", None),
        ("inquiry_text", ""),
        ("followup_text", ""),
    ):
        st.session_state.setdefault(key, default)

    if not account.is_broker:
        st.caption(f"Welcome, {account.display_name}. Tell us what you are looking for.")
        buyer.render(account)
        return

    st.caption(
        "Which inquiries deserve a broker's immediate attention, which need more "
        "qualification, and which should be deprioritised?"
    )
    st.session_state.setdefault("active_view", BROKER_VIEWS[0])

    # st.tabs resets to the first tab on every rerun, which would strand anyone
    # who navigates here from the dashboard. A keyed selector survives reruns.
    pending = st.session_state.pop("pending_view", None)
    if pending in BROKER_VIEWS:
        st.session_state["active_view"] = pending

    view = st.radio(
        "View", BROKER_VIEWS, key="active_view", horizontal=True,
        label_visibility="collapsed",
    )
    st.divider()

    if view == BROKER_VIEWS[0]:
        new_lead.render()
    elif view == BROKER_VIEWS[1]:
        analysis.render()
    elif view == BROKER_VIEWS[2]:
        dashboard.render()
    else:
        properties.render()


if __name__ == "__main__":
    main()
