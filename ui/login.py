"""The sign-in screen.

Two doors into the same agent: buyers submit inquiries and follow their own
lead; brokers see the whole pipeline. See ``services/auth.py`` for why this is
demo access control rather than authentication.
"""

from __future__ import annotations

import streamlit as st

from services import auth


def _submit(role: str, display_name: str, access_code: str = "") -> None:
    try:
        account = auth.sign_in(role, display_name, access_code)
    except auth.SignInError as exc:
        st.session_state["login_error"] = str(exc)
        return
    auth.store_account(st.session_state, account)
    st.session_state["login_error"] = None


def render() -> None:
    st.subheader("Sign in")
    st.caption(
        "Choose how you want to use the app. Buyers submit an inquiry and follow "
        "their own lead; brokers see the full pipeline, every lead and the inventory."
    )

    if st.session_state.get("login_error"):
        st.error(st.session_state["login_error"])

    buyer_tab, broker_tab = st.tabs(["I'm a buyer", "I'm a broker"])

    with buyer_tab:
        st.markdown("**Buyer**")
        st.caption(
            "Describe what you are looking for in your own words. The agent will "
            "ask follow-up questions, search the inventory and tell you where your "
            "enquiry stands."
        )
        with st.form("buyer_login"):
            name = st.text_input(
                "Your name",
                placeholder="e.g. Rahul Nair",
                help="Used to label your enquiries. Sign in with the same name to "
                     "come back to them.",
            )
            if st.form_submit_button("Continue as buyer", type="primary",
                                     width="stretch"):
                _submit(auth.BUYER, name)
                st.rerun()

    with broker_tab:
        st.markdown("**Broker**")
        st.caption(
            "Full access: the lead pipeline, every buyer conversation, agent "
            "reasoning, decision history and the property inventory."
        )
        with st.form("broker_login"):
            broker_name = st.text_input("Your name", placeholder="e.g. Priya (Sales Desk)")
            code = st.text_input(
                "Broker access code",
                type="password",
                help="A shared demo code, not a personal password.",
            )
            if st.form_submit_button("Continue as broker", type="primary",
                                     width="stretch"):
                _submit(auth.BROKER, broker_name, code)
                st.rerun()

        st.info(
            f"Demo access code: `{auth.broker_access_code()}` — "
            "set `BROKER_ACCESS_CODE` in `.env` to change it."
        )

    st.divider()
    st.caption(
        "**This sign-in is a demo role switch, not a security system.** There are "
        "no accounts, no passwords are stored, and the broker code is a single "
        "shared value kept in plain text. Do not put real data behind it."
    )
