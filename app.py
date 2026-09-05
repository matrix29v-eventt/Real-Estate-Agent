import streamlit as st
import json
from datetime import datetime
from services.database import (
    init_db,
    seed_data,
    get_all_properties,
    get_all_leads,
    get_lead_by_id,
    get_actions_for_lead,
    get_lead_metrics,
)
from services.agent import (
    process_inquiry,
    follow_up_inquiry,
    generate_email_draft,
    generate_broker_summary,
)
from services.property_matcher import match_properties


def init_app():
    init_db()
    seed_data()


def main():
    st.set_page_config(
        page_title="Real Estate Lead Qualifier", page_icon="🏠", layout="wide"
    )
    init_app()

    st.title("🏠 Real Estate Lead Qualification & Routing Agent")
    st.markdown("### AI-Powered Lead Qualification for Brokers")

    tab1, tab2, tab3 = st.tabs(
        ["📝 New Lead / Agent Conversation", "🔍 Lead Analysis", "📊 Lead Dashboard"]
    )

    with tab1:
        render_conversation_tab()

    with tab2:
        render_analysis_tab()

    with tab3:
        render_dashboard_tab()


def render_conversation_tab():
    st.header("New Lead / Agent Conversation")

    col1, col2 = st.columns([1, 2])
    with col1:
        name = st.text_input("Buyer Name (optional)", key="buyer_name")
        inquiry = st.text_area(
            "Enter property inquiry",
            height=150,
            placeholder="e.g., Looking for a 3BHK apartment around Technopark. Budget 65-75 lakh. Planning to buy within 2 months.",
        )
        submit_inquiry = st.button("Analyze Lead", type="primary")

    with col2:
        if "current_lead" not in st.session_state:
            st.session_state.current_lead = None
        if "conversation" not in st.session_state:
            st.session_state.conversation = []
        if "lead_id" not in st.session_state:
            st.session_state.lead_id = None

    if submit_inquiry and inquiry.strip():
        if not name.strip():
            name = "Anonymous"
        st.session_state.conversation = []
        st.session_state.current_lead = None
        result = process_inquiry(name, inquiry)
        st.session_state.current_lead = result["lead_data"]
        st.session_state.conversation = [
            {"sender": "buyer", "message": inquiry, "type": "inquiry"}
        ]
        st.session_state.lead_id = result["lead_data"]["lead_id"]
        st.session_state.follow_up_result = result
        st.session_state.current_matches = result["matches"]
        st.rerun()

    if "current_lead" in st.session_state and st.session_state.current_lead:
        lead = st.session_state.current_lead
        st.markdown("---")
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader(f"👤 Lead: {lead['name']} ({lead['lead_id']})")
            st.metric("Intent Score", f"{lead['intent_score']}/100")
            tier_color = {
                "HIGH": "🟢",
                "MEDIUM": "🟡",
                "LOW": "🔴",
                "NEEDS_CLARIFICATION": "🟠",
            }
            st.markdown(
                f"**Intent Tier:** {tier_color.get(lead['intent_tier'], '')} {lead['intent_tier']}"
            )
            st.markdown(f"**Status:** {lead['status']}")
            st.markdown(f"**Current Action:** {lead['current_action']}")

        with col2:
            st.subheader("📋 Extracted Requirements")
            req = lead.get("parsed_requirements", {})
            budget = (
                req.get("budget_min")
                and req.get("budget_max")
                and f"₹{req['budget_min'] / 100000:.1f} - ₹{req['budget_max'] / 100000:.1f} Lakh"
                or "Not specified"
            )
            locations = ", ".join(req.get("locations", [])) or "Not specified"
            st.write(f"**Budget:** {budget}")
            st.write(f"**Location:** {locations}")
            st.write(f"**BHK:** {req.get('bhk', 'Not specified')}")
            st.write(
                f"**Timeline:** {req.get('timeline_months', 'Not specified')} months"
            )
            st.write(f"**Financing:** {req.get('financing', 'Not specified')}")
            if req.get("financing_ready"):
                st.write("✅ Financing Ready")
            st.write(f"**Parking:** {req.get('parking', 'Not specified')}")
            st.write(f"**Purpose:** {req.get('purpose', 'Not specified')}")

    if "current_lead" in st.session_state and st.session_state.current_lead:
        lead = st.session_state.current_lead
        st.markdown("---")
        st.subheader("💬 Follow-up Conversation")

        if st.session_state.conversation:
            for msg in st.session_state.conversation:
                if msg["sender"] == "buyer":
                    st.chat_message("user").write(msg["message"])
                elif msg["sender"] == "agent":
                    st.chat_message("assistant").write(msg["message"])

        with st.form("follow_up_form"):
            response = st.text_input(
                "Buyer's response", placeholder="Type the buyer's reply here..."
            )
            submitted = st.form_submit_button("Send Response")
            if submitted and response.strip():
                result = follow_up_inquiry(
                    st.session_state.lead_id,
                    st.session_state.current_lead["name"],
                    response,
                    st.session_state.current_lead,
                )
                st.session_state.conversation.append(
                    {"sender": "buyer", "message": response}
                )
                st.session_state.conversation.append(
                    {
                        "sender": "agent",
                        "message": result["llm_response"]["follow_up_question"]
                        or "Thank you! I've updated the lead profile.",
                    }
                )
                st.session_state.current_lead = result["lead_data"]
                st.session_state.follow_up_result = result
                st.rerun()

        follow_up_question = None
        if "follow_up_result" in st.session_state and st.session_state.follow_up_result:
            follow_up_question = st.session_state.follow_up_result["llm_response"].get(
                "follow_up_question"
            )

        if follow_up_question and "current_lead" in st.session_state:
            st.info(f"🔔 Agent Follow-up Question: {follow_up_question}")

        if (
            not follow_up_question
            and "current_lead" in st.session_state
            and st.session_state.current_lead
        ):
            lead = st.session_state.current_lead
            decision = lead.get("current_action", "")
            if decision == "ESCALATE_TO_BROKER":
                st.success(
                    f"🎉 Great news! Your lead has been flagged as HIGH INTENT ({lead['intent_score']}/100). A broker will be in touch with you shortly to schedule a property viewing. Thank you for your interest!"
                )
                st.markdown("**📋 What happens next:**")
                st.write("1. A broker will contact you at the provided contact details")
                st.write("2. They will discuss the best matching properties")
                st.write("3. A property viewing will be scheduled at your convenience")
                from services.agent import generate_broker_summary

                matches = st.session_state.get("current_matches", [])
                summary = generate_broker_summary(lead, matches[:3])
                with st.expander("📄 Broker Internal Summary (click to view)"):
                    st.text_area("Broker Summary", value=summary, height=200)
            elif decision == "SHOW_MATCHING_PROPERTIES":
                st.success(
                    f"🔍 We found matching properties for your requirements! Below are the top picks."
                )
                from services.property_matcher import match_properties
                from data.properties import PROPERTIES as ALL_PROPS

                req = lead.get("parsed_requirements", {})
                matches = match_properties(req, ALL_PROPS)
                st.session_state["current_matches"] = matches
                for m in matches[:5]:
                    p = m["property"]
                    st.markdown(
                        f"**{p['name']}** — {p['location']} | {p['bhk']}BHK | ₹{p['price'] / 100000:.1f}L | {m['match_score']}% match | {p['availability']} | {p['furnishing']}"
                    )
                    for r in m["reasons"][:3]:
                        st.write(f"  • {r}")
                st.markdown("---")
                st.info(
                    "If any property interests you, a broker can arrange a viewing. Just reply below!"
                )
            else:
                st.info("✅ Lead profile updated. Continue conversation if needed.")


def render_analysis_tab():
    st.header("Lead Analysis")

    if "current_lead" not in st.session_state or not st.session_state.current_lead:
        st.warning(
            "⚠️ No lead loaded. Start by entering an inquiry in the **New Lead** tab."
        )
        return

    lead = st.session_state.current_lead
    llm_resp = None
    try:
        from services.agent import analyze_lead

        result_data = analyze_lead(
            lead["name"],
            lead["original_inquiry"],
            lead.get("parsed_requirements", {}),
            lead.get("conversation_history", []),
            lead["lead_id"],
            lead,
        )
        llm_resp = result_data
        st.session_state.current_lead = llm_resp["lead_data"]
    except:
        pass

    req = lead.get("parsed_requirements", {})
    budget = (
        req.get("budget_min")
        and req.get("budget_max")
        and f"₹{req['budget_min'] / 100000:.1f} - ₹{req['budget_max'] / 100000:.1f} Lakh"
        or "Not specified"
    )
    locations = ", ".join(req.get("locations", [])) or "Not specified"
    bhk = req.get("bhk", "Not specified")
    timeline = req.get("timeline_months", "Not specified")
    financing = req.get("financing", "Not specified")
    financing_ready = req.get("financing_ready", False)
    parking = req.get("parking", "Not specified")
    purpose = req.get("purpose", "Not specified")

    tier_color = {
        "HIGH": "🟢",
        "MEDIUM": "🟡",
        "LOW": "🔴",
        "NEEDS_CLARIFICATION": "🟠",
    }

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Buyer Intent", f"{lead['intent_tier']}", f"{lead['intent_score']}/100"
        )
    with col2:
        st.metric("Next Action", lead["current_action"])
    with col3:
        st.metric("Status", lead["status"])

    st.markdown("---")
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📋 Extracted Requirements")
        st.write(f"**Budget:** {budget}")
        st.write(f"**Location:** {locations}")
        st.write(f"**BHK:** {bhk}")
        st.write(f"**Timeline:** {timeline} months")
        st.write(f"**Financing:** {financing}")
        if financing_ready:
            st.success("✅ Financing Ready")
        st.write(f"**Parking:** {parking}")
        st.write(f"**Purpose:** {purpose}")

    with col2:
        st.subheader("🎯 Agent Reasoning")
        reasoning = (
            llm_resp["llm_response"]["reasoning"]
            if llm_resp
            else lead.get("decision_history", [{}])[-1].get("reasoning", [])
        )
        if isinstance(reasoning, list):
            for r in reasoning:
                st.write(f"• {r}")
        else:
            st.write(reasoning)

        missing = llm_resp["llm_response"]["missing_information"] if llm_resp else []
        if missing:
            st.write(f"**Missing:** {', '.join(missing)}")

        risks = llm_resp["llm_response"]["risks"] if llm_resp else []
        if risks:
            st.warning(f"**Risks:** {', '.join(risks)}")

    st.markdown("---")
    st.subheader("🏠 Property Matches")
    matches = llm_resp["matches"] if llm_resp else []
    if matches:
        for m in matches[:5]:
            prop = m["property"]
            st.markdown(f"""
            **{prop["name"]}** — {prop["location"]}
            | {prop["bhk"]}BHK | ₹{prop["price"] / 100000:.1f}L | {prop["sqft"]} sqft | {prop["parking"]} parking | {prop["availability"]}
            *Match: {m["match_score"]}% — {", ".join(m["reasons"][:3])}*
            """)
    else:
        st.info("No matching properties found.")

    st.markdown("---")
    st.subheader("📧 Recommended Business Action")
    next_step = (
        llm_resp["llm_response"]["recommended_next_step"]
        if llm_resp
        else lead.get("current_action", "")
    )
    st.write(f"**Action:** {next_step}")

    email_draft = generate_email_draft(lead, matches[:3])
    broker_summary = generate_broker_summary(lead, matches[:3])

    col1, col2 = st.columns(2)
    with col1:
        st.write("**📧 Buyer Email Draft:**")
        st.text_area("Email Draft", value=email_draft, height=200)
    with col2:
        st.write("**📋 Broker Summary:**")
        st.text_area("Broker Summary", value=broker_summary, height=200)


def render_dashboard_tab():
    st.header("Lead Dashboard")

    metrics = get_lead_metrics()
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Leads", metrics["total"])
    col2.metric("High Intent", metrics["high"])
    col3.metric("Medium Intent", metrics["medium"])
    col4.metric("Needs Clarification", metrics["needs_clarification"])
    col5.metric("Escalated", metrics["escalated"])
    col6.metric("Low Priority", metrics["low_priority"])

    st.markdown("---")
    leads = get_all_leads()

    st.subheader("All Leads")
    for lead in leads:
        tier_color = {
            "HIGH": "🟢",
            "MEDIUM": "🟡",
            "LOW": "🔴",
            "NEEDS_CLARIFICATION": "🟠",
        }
        expander = st.expander(
            f"{lead['name']} ({lead['lead_id']}) — {tier_color.get(lead['intent_tier'], '')} {lead['intent_tier']} ({lead['intent_score']}/100) — {lead['current_action']}",
            expanded=False,
        )
        with expander:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.write(f"**Inquiry:** {lead['original_inquiry']}")
                req = lead.get("parsed_requirements", {})
                budget = (
                    req.get("budget_min")
                    and req.get("budget_max")
                    and f"₹{req['budget_min'] / 100000:.1f}-{req['budget_max'] / 100000:.1f}L"
                    or "TBD"
                )
                locations = ", ".join(req.get("locations", [])) or "TBD"
                st.write(
                    f"**Budget:** {budget} | **Location:** {locations} | **BHK:** {req.get('bhk', 'N/A')} | **Timeline:** {req.get('timeline_months', 'N/A')}mo"
                )
                st.write(
                    f"**Status:** {lead['status']} | **Updated:** {lead['updated_at']}"
                )

                actions = get_actions_for_lead(lead["lead_id"])
                if actions:
                    st.write("**Decision History:**")
                    for a in actions:
                        st.write(
                            f"- {a['timestamp']}: {a['decision']} (Score: {a['intent_score']})"
                        )

            with col2:
                if lead.get("decision_history"):
                    last_decision = lead["decision_history"][-1]
                    st.write(f"**Last Reasoning:**")
                    for r in last_decision.get("reasoning", []):
                        st.write(f"• {r}")

                if lead.get("conversation_history"):
                    st.write("**Conversation:**")
                    for msg in lead["conversation_history"]:
                        st.write(
                            f"- {msg.get('sender', 'unknown')}: {msg.get('message', '')}"
                        )

                lead_obj = {
                    "lead_id": lead["lead_id"],
                    "name": lead["name"],
                    "original_inquiry": lead["original_inquiry"],
                    "parsed_requirements": req,
                    "intent_score": lead["intent_score"],
                    "intent_tier": lead["intent_tier"],
                    "status": lead["status"],
                    "current_action": lead["current_action"],
                    "created_at": lead["created_at"],
                    "updated_at": lead["updated_at"],
                    "conversation_history": lead.get("conversation_history", []),
                    "decision_history": lead.get("decision_history", []),
                }

                if st.button(
                    f"🔍 Analyze {lead['name']}", key=f"analyze_{lead['lead_id']}"
                ):
                    from services.agent import analyze_lead

                    result = analyze_lead(
                        lead["name"],
                        lead["original_inquiry"],
                        lead.get("parsed_requirements", {}),
                        lead.get("conversation_history", []),
                        lead["lead_id"],
                        lead_obj,
                    )
                    st.session_state.current_lead = result["lead_data"]
                    st.session_state.conversation = [
                        {"sender": "buyer", "message": lead["original_inquiry"]}
                    ]
                    st.session_state.lead_id = lead["lead_id"]
                    st.rerun()


if __name__ == "__main__":
    main()
