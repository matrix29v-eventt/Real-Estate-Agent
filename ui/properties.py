"""Broker-only inventory view.

The catalogue the matching engine actually searches, shown in full so a broker
can see why a lead did or did not find anything.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from models.schemas import money
from services import db


def _frame() -> pd.DataFrame:
    rows = []
    for prop in db.list_properties():
        rows.append(
            {
                "ID": prop["property_id"],
                "Property": prop["name"],
                "Area": prop["location"],
                "Type": prop["property_type"],
                "BHK": prop["bhk"] if prop["bhk"] is not None else "-",
                "Sqft": prop["sqft"],
                "Price": prop["price"],
                "Parking": "Yes" if prop["parking"] else "No",
                "Furnishing": prop["furnishing"] or "-",
                "Availability": prop["availability"],
                "Possession": prop["possession_status"] or "-",
                "Builder": prop["builder"] or "-",
                "Amenities": ", ".join(prop["amenities"]),
                "Tags": ", ".join(prop["tags"]),
            }
        )
    return pd.DataFrame(rows)


def render() -> None:
    st.subheader("Property inventory")
    frame = _frame()
    if frame.empty:
        st.info("No properties in the database.")
        return

    available = frame[frame["Availability"] == "AVAILABLE"]
    cols = st.columns(4)
    cols[0].metric("Total listings", len(frame))
    cols[1].metric("Available", len(available))
    cols[2].metric("Areas covered", frame["Area"].nunique())
    cols[3].metric(
        "Entry price",
        money(int(available["Price"].min())) if not available.empty else "-",
    )

    st.divider()

    filters = st.columns(4)
    area = filters[0].selectbox("Area", ["All"] + sorted(frame["Area"].unique()))
    ptype = filters[1].selectbox("Type", ["All"] + sorted(frame["Type"].unique()))
    bhk_values = sorted(str(b) for b in frame["BHK"].unique())
    bhk = filters[2].selectbox("BHK", ["All"] + bhk_values)
    availability = filters[3].selectbox(
        "Availability", ["All"] + sorted(frame["Availability"].unique())
    )

    low, high = int(frame["Price"].min()), int(frame["Price"].max())
    budget = st.slider(
        "Price range", min_value=low, max_value=high, value=(low, high), step=100_000,
        format="%d",
    )
    st.caption(f"Showing {money(budget[0])} to {money(budget[1])}")

    view = frame.copy()
    if area != "All":
        view = view[view["Area"] == area]
    if ptype != "All":
        view = view[view["Type"] == ptype]
    if bhk != "All":
        view = view[view["BHK"].astype(str) == bhk]
    if availability != "All":
        view = view[view["Availability"] == availability]
    view = view[(view["Price"] >= budget[0]) & (view["Price"] <= budget[1])]

    st.caption(f"{len(view)} of {len(frame)} listings match these filters.")
    display = view.copy()
    display["Price"] = display["Price"].map(lambda p: money(int(p)))
    st.dataframe(display.sort_values("ID"), hide_index=True, width="stretch")

    st.caption(
        "This inventory is synthetic and deliberately uneven — there is no 4BHK "
        "below Rs 1.42 Cr and nothing in Kowdiar below Rs 95 L — so the agent has "
        "to reason about budgets that cannot be met."
    )
