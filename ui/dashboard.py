"""Tab C - broker-facing lead dashboard."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services import db
from ui import components
from ui.analysis import rebuild_from_db


def _leads_frame() -> pd.DataFrame:
    rows = []
    for lead in db.list_leads():
        rows.append(
            {
                "Lead": lead["lead_id"],
                "Name": lead.get("name") or "-",
                "Intent score": lead.get("intent_score") or 0,
                "Tier": lead.get("intent_tier") or "-",
                "Status": lead.get("status") or "-",
                "Recommended action": components.ACTION_LABELS.get(
                    lead.get("current_action") or "", lead.get("current_action") or "-"
                ),
                "Updated": (lead.get("updated_at") or "")[:16].replace("T", " "),
            }
        )
    return pd.DataFrame(rows)


def render() -> None:
    st.subheader("Lead dashboard")
    metrics = db.dashboard_metrics()

    row1 = st.columns(4)
    row1[0].metric("Total leads", metrics["total_leads"])
    row1[1].metric("High intent", metrics["high_intent"])
    row1[2].metric("Medium intent", metrics["medium_intent"])
    row1[3].metric("Needs clarification", metrics["needs_clarification"])

    row2 = st.columns(4)
    row2[0].metric("Broker escalations", metrics["broker_escalations"])
    row2[1].metric("Nurturing", metrics["nurturing"])
    row2[2].metric("Low priority", metrics["low_priority"])
    row2[3].metric("Decisions logged", metrics["decisions_logged"])

    st.divider()

    frame = _leads_frame()
    if frame.empty:
        st.info("No leads yet.")
        return

    tiers = ["All"] + sorted(t for t in frame["Tier"].unique() if t != "-")
    statuses = ["All"] + sorted(s for s in frame["Status"].unique() if s != "-")
    filter_cols = st.columns(3)
    tier_filter = filter_cols[0].selectbox("Filter by tier", tiers)
    status_filter = filter_cols[1].selectbox("Filter by status", statuses)
    search = filter_cols[2].text_input("Search name or lead id", "")

    view = frame.copy()
    if tier_filter != "All":
        view = view[view["Tier"] == tier_filter]
    if status_filter != "All":
        view = view[view["Status"] == status_filter]
    if search.strip():
        needle = search.strip().lower()
        view = view[
            view["Name"].str.lower().str.contains(needle)
            | view["Lead"].str.lower().str.contains(needle)
        ]

    view = view.sort_values("Intent score", ascending=False)
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "Intent score": st.column_config.ProgressColumn(
                "Intent score", min_value=0, max_value=100, format="%d"
            )
        },
    )

    st.divider()
    st.markdown("### Inspect a lead")
    options = view["Lead"].tolist() or frame["Lead"].tolist()
    default_index = 0
    active = st.session_state.get("active_lead_id")
    if active in options:
        default_index = options.index(active)
    selected = st.selectbox("Lead", options, index=default_index)

    if st.button("Open in Lead Analysis tab"):
        st.session_state["active_lead_id"] = selected
        st.session_state["last_result"] = None
        st.success(f"Lead {selected} is now active — open the **Lead Analysis** tab.")

    lead = db.get_lead(selected) or {}
    result = rebuild_from_db(selected)

    st.markdown("**Structured summary**")
    components.render_summary(lead.get("summary") or {})

    tabs = st.tabs(["Conversation", "Property matches", "Decision history"])
    with tabs[0]:
        components.render_conversation(db.get_turns(selected))
    with tabs[1]:
        if result:
            components.render_matches(
                result.matches,
                meaningful=bool(
                    result.evidence.inventory_stats.get("matching_is_meaningful", True)
                ),
            )
            st.caption("Matches are recomputed against current inventory each time.")
        else:
            st.caption("No stored requirements to match against.")
    with tabs[2]:
        components.render_decision_history(db.get_actions(selected))
