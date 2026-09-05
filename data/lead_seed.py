"""Historical lead seed data.

Twenty leads spanning every quality band the broker actually sees: hot buyers,
warm-but-incomplete inquiries, unrealistic budgets, long-horizon browsers and
tyre-kickers. Each seeded lead carries its conversation and one archived agent
decision so the dashboard and the audit trail are populated on first launch.

These records were produced by earlier (simulated) agent runs; live runs replace
and extend them through the same code path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from services import db

_NOW = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def _ts(days_ago: float) -> str:
    return (_NOW - timedelta(days=days_ago)).replace(microsecond=0).isoformat()


def _reqs(**kwargs: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": None, "contact": None, "budget_min": None, "budget_max": None,
        "locations": [], "property_type": None, "bhk": None, "min_sqft": None,
        "timeline_months": None, "timeline_text": None, "financing_method": None,
        "financing_readiness": "UNKNOWN", "amenities": [], "parking_required": None,
        "furnishing": None, "purpose": "UNKNOWN", "viewing_ready": None,
        "notes": [], "original_inquiry": None,
    }
    base.update(kwargs)
    return base


SEED_LEADS: List[Dict[str, Any]] = [
    {
        "lead_id": "L001", "name": "Rahul Nair", "contact": "rahul.n@example.com",
        "days_ago": 2.0,
        "inquiry": "Looking for a 3BHK near Technopark, budget around 70-78 lakh. "
                   "Loan sanctioned, want to close within 6 weeks. Parking is a must.",
        "reqs": _reqs(name="Rahul Nair", budget_min=7_000_000, budget_max=7_800_000,
                      locations=["Technopark", "Kazhakkoottam"], property_type="Apartment",
                      bhk=3, timeline_months=1.5, timeline_text="within 6 weeks",
                      financing_method="Home loan", financing_readiness="APPROVED",
                      parking_required=True, purpose="SELF_USE", viewing_ready=True,
                      amenities=["Gated Community"]),
        "score": 91, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Broker should call today and line up viewings for P001, P008 and P003.",
        "reasoning": ["Loan already sanctioned and a 6-week closing window",
                      "Budget sits squarely inside available Technopark corridor stock",
                      "Three ready-to-move matches above 85% compatibility"],
        "turns": [("buyer", "Looking for a 3BHK near Technopark, budget around 70-78 lakh. "
                            "Loan sanctioned, want to close within 6 weeks. Parking is a must."),
                  ("agent", "Escalating to a broker - strong budget/timeline fit with three ready matches.")],
    },
    {
        "lead_id": "L002", "name": "Anjali Menon", "contact": "anjali.menon@example.com",
        "days_ago": 3.0,
        "inquiry": "We want a 2BHK in Sreekaryam or Ulloor under 55 lakh, moving in about 4 months.",
        "reqs": _reqs(name="Anjali Menon", budget_max=5_500_000,
                      locations=["Sreekaryam", "Ulloor"], property_type="Apartment", bhk=2,
                      timeline_months=4, timeline_text="about 4 months",
                      financing_method="Home loan", financing_readiness="IN_PROGRESS",
                      purpose="SELF_USE", parking_required=True),
        "score": 74, "tier": "MEDIUM", "status": "QUALIFYING",
        "action": "SHOW_MATCHING_PROPERTIES",
        "next_step": "Share the shortlist and confirm whether the loan pre-approval has come through.",
        "reasoning": ["Clear budget and two specific locations",
                      "Four-month horizon is real but not urgent",
                      "Loan is applied for but not yet sanctioned"],
        "turns": [("buyer", "We want a 2BHK in Sreekaryam or Ulloor under 55 lakh, moving in about 4 months."),
                  ("agent", "Shared four matching 2BHK options and asked about loan status.")],
    },
    {
        "lead_id": "L003", "name": "Vishnu Prasad", "contact": None, "days_ago": 1.0,
        "inquiry": "I need a nice flat in Trivandrum.",
        "reqs": _reqs(name="Vishnu Prasad", locations=["Thiruvananthapuram"],
                      property_type="Apartment"),
        "score": 22, "tier": "NEEDS_CLARIFICATION", "status": "NEEDS_INFORMATION",
        "action": "ASK_MORE_INFO",
        "next_step": "Ask for budget range, preferred areas and purchase timeline before any broker time is spent.",
        "reasoning": ["No budget, no specific area, no timeline",
                      "Trivandrum-wide inventory spans Rs 27 L to Rs 3.2 Cr, so matching is meaningless",
                      "Cannot assess seriousness from a single vague sentence"],
        "turns": [("buyer", "I need a nice flat in Trivandrum."),
                  ("agent", "Asked for budget, preferred areas and timeline.")],
    },
    {
        "lead_id": "L004", "name": "Fathima Rasheed", "contact": "fathima.r@example.com",
        "days_ago": 5.0,
        "inquiry": "4BHK premium property in Kowdiar, my budget is 25 lakh.",
        "reqs": _reqs(name="Fathima Rasheed", budget_max=2_500_000, locations=["Kowdiar"],
                      bhk=4, property_type="Apartment", purpose="SELF_USE"),
        "score": 18, "tier": "LOW", "status": "LOW_PRIORITY",
        "action": "RESET_EXPECTATIONS",
        "next_step": "Send the budget-reality note offering Thampanoor/Kesavadasapuram alternatives; no broker time yet.",
        "reasoning": ["Cheapest Kowdiar listing is Rs 95 L, roughly 4x the stated budget",
                      "No 4BHK anywhere in inventory below Rs 1.42 Cr",
                      "Zero viable matches, so escalation would waste broker time"],
        "turns": [("buyer", "4BHK premium property in Kowdiar, my budget is 25 lakh."),
                  ("agent", "Explained the Kowdiar price floor and offered alternative areas.")],
    },
    {
        "lead_id": "L005", "name": "Arun Kumar", "contact": "arun.k@example.com", "days_ago": 7.0,
        "inquiry": "Looking at 3BHK properties around 80 lakh but probably won't buy for another 18 months.",
        "reqs": _reqs(name="Arun Kumar", budget_max=8_000_000, locations=["Pattom", "Ulloor"],
                      bhk=3, property_type="Apartment", timeline_months=18,
                      timeline_text="about 18 months", purpose="SELF_USE"),
        "score": 47, "tier": "LOW", "status": "NURTURING",
        "action": "NURTURE_LEAD",
        "next_step": "Add to the quarterly market-update list and re-check in 6 months.",
        "reasoning": ["Budget and configuration are realistic for Pattom/Ulloor",
                      "18-month horizon means today's inventory will have turned over",
                      "No financing activity started"],
        "turns": [("buyer", "Looking at 3BHK properties around 80 lakh but probably won't buy for another 18 months."),
                  ("agent", "Placed on the long-term nurture list with a 6-month check-in.")],
    },
    {
        "lead_id": "L006", "name": "Deepa Suresh", "contact": "deepa.s@example.com", "days_ago": 4.0,
        "inquiry": "Investment flat near Technopark, ready to move, up to 60 lakh. Cash purchase, "
                   "can decide this month.",
        "reqs": _reqs(name="Deepa Suresh", budget_max=6_000_000,
                      locations=["Technopark", "Kazhakkoottam"], property_type="Apartment",
                      timeline_months=1, timeline_text="this month",
                      financing_method="Own funds", financing_readiness="APPROVED",
                      purpose="INVESTMENT", viewing_ready=True),
        "score": 86, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Broker to present the rental-yield comparison for P009 and P002 within 24 hours.",
        "reasoning": ["Cash buyer with a one-month decision window",
                      "Investment purpose plus ready-to-move filter narrows to two strong matches",
                      "No financing dependency to slow the deal"],
        "turns": [("buyer", "Investment flat near Technopark, ready to move, up to 60 lakh. "
                            "Cash purchase, can decide this month."),
                  ("agent", "Escalated - cash buyer, immediate timeline, two solid yield options.")],
    },
    {
        "lead_id": "L007", "name": "Sanjay Pillai", "contact": None, "days_ago": 6.0,
        "inquiry": "What is the price of flats in Kowdiar? Just checking for now.",
        "reqs": _reqs(name="Sanjay Pillai", locations=["Kowdiar"], purpose="UNKNOWN"),
        "score": 15, "tier": "LOW", "status": "LOW_PRIORITY",
        "action": "LOW_PRIORITY_OR_DISCARD",
        "next_step": "Send the Kowdiar price sheet automatically; no broker follow-up.",
        "reasoning": ["Explicitly browsing, no budget or timeline offered",
                      "Price enquiry only, no configuration stated",
                      "Two prior contacts produced no additional detail"],
        "turns": [("buyer", "What is the price of flats in Kowdiar? Just checking for now."),
                  ("agent", "Sent the price band summary; kept off the broker queue.")],
    },
    {
        "lead_id": "L008", "name": "Meera Krishnan", "contact": "meera.k@example.com", "days_ago": 2.5,
        "inquiry": "Need a 3BHK villa with garden in Peroorkada, budget 1 to 1.1 crore, within 3 months. "
                   "Loan process started.",
        "reqs": _reqs(name="Meera Krishnan", budget_min=10_000_000, budget_max=11_000_000,
                      locations=["Peroorkada"], property_type="Villa", bhk=3, timeline_months=3,
                      timeline_text="within 3 months", financing_method="Home loan",
                      financing_readiness="IN_PROGRESS", amenities=["Landscaped Garden"],
                      parking_required=True, purpose="SELF_USE", viewing_ready=True),
        "score": 83, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Arrange a site visit at Peroorkada Villa Grove this week.",
        "reasoning": ["Exact villa match available at Rs 1.05 Cr inside the stated band",
                      "Three-month timeline with loan already in progress",
                      "Buyer has confirmed willingness to view"],
        "turns": [("buyer", "Need a 3BHK villa with garden in Peroorkada, budget 1 to 1.1 crore, "
                            "within 3 months. Loan process started."),
                  ("agent", "Escalated with a single exact villa match for immediate viewing.")],
    },
    {
        "lead_id": "L009", "name": "Nithin Raj", "contact": "nithin.raj@example.com", "days_ago": 9.0,
        "inquiry": "Something around 45 lakh, 2BHK, anywhere decent in the city.",
        "reqs": _reqs(name="Nithin Raj", budget_max=4_500_000, bhk=2, property_type="Apartment"),
        "score": 41, "tier": "NEEDS_CLARIFICATION", "status": "NEEDS_INFORMATION",
        "action": "ASK_MORE_INFO",
        "next_step": "Ask which side of the city and when they intend to buy.",
        "reasoning": ["Budget and configuration are clear, location is not",
                      "Six candidate properties across four very different areas",
                      "No timeline stated after the first exchange"],
        "turns": [("buyer", "Something around 45 lakh, 2BHK, anywhere decent in the city."),
                  ("agent", "Asked for preferred areas and purchase timeline.")],
    },
    {
        "lead_id": "L010", "name": "Priya Varghese", "contact": "priya.v@example.com", "days_ago": 11.0,
        "inquiry": "Fully furnished 3BHK in Vazhuthacaud or Kowdiar, 1.2 to 1.4 crore, buying in 2 months, "
                   "loan pre-approved.",
        "reqs": _reqs(name="Priya Varghese", budget_min=12_000_000, budget_max=14_000_000,
                      locations=["Vazhuthacaud", "Kowdiar"], property_type="Apartment", bhk=3,
                      timeline_months=2, timeline_text="2 months", financing_method="Home loan",
                      financing_readiness="APPROVED", furnishing="Fully-Furnished",
                      parking_required=True, purpose="SELF_USE", viewing_ready=True),
        "score": 89, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Broker to schedule back-to-back viewings of P035 and P037.",
        "reasoning": ["Pre-approved loan and a two-month window",
                      "Furnishing preference matches P035 exactly",
                      "Budget band contains two premium listings"],
        "turns": [("buyer", "Fully furnished 3BHK in Vazhuthacaud or Kowdiar, 1.2 to 1.4 crore, "
                            "buying in 2 months, loan pre-approved."),
                  ("agent", "Escalated with two furnished premium matches.")],
    },
    {
        "lead_id": "L011", "name": "Tom Jacob", "contact": None, "days_ago": 14.0,
        "inquiry": "Do you have any 1BHK cheap flats? Maybe for rent later.",
        "reqs": _reqs(name="Tom Jacob", bhk=1, purpose="INVESTMENT"),
        "score": 33, "tier": "LOW", "status": "NURTURING",
        "action": "NURTURE_LEAD",
        "next_step": "Send the two 1BHK investment options and revisit if a reply arrives.",
        "reasoning": ["Only two 1BHK units exist, both under Rs 32 L",
                      "No budget or timeline given, purchase intent uncertain",
                      "Rental framing suggests exploratory investment interest"],
        "turns": [("buyer", "Do you have any 1BHK cheap flats? Maybe for rent later."),
                  ("agent", "Shared the two 1BHK options and kept the lead warm.")],
    },
    {
        "lead_id": "L012", "name": "Lakshmi Iyer", "contact": "lakshmi.iyer@example.com", "days_ago": 8.0,
        "inquiry": "3BHK gated community in Kazhakkoottam, 65-72 lakh, need it ready to move, "
                   "shifting in 3 months for a new job.",
        "reqs": _reqs(name="Lakshmi Iyer", budget_min=6_500_000, budget_max=7_200_000,
                      locations=["Kazhakkoottam"], property_type="Apartment", bhk=3,
                      timeline_months=3, timeline_text="3 months, job relocation",
                      financing_method="Home loan", financing_readiness="IN_PROGRESS",
                      amenities=["Gated Community"], parking_required=True,
                      purpose="SELF_USE", viewing_ready=True),
        "score": 85, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Broker to confirm P001 and P005 availability and offer weekend viewings.",
        "reasoning": ["Relocation deadline creates genuine urgency",
                      "Two ready-to-move gated projects sit inside the band",
                      "Amenity and parking requirements are both satisfied"],
        "turns": [("buyer", "3BHK gated community in Kazhakkoottam, 65-72 lakh, need it ready to move, "
                            "shifting in 3 months for a new job."),
                  ("agent", "Escalated with two exact gated-community matches.")],
    },
    {
        "lead_id": "L013", "name": "Rakesh Menon", "contact": "rakesh.m@example.com", "days_ago": 12.0,
        "inquiry": "First I said 50 lakh, but actually maybe 1.5 crore is fine. Or a plot. Not sure yet.",
        "reqs": _reqs(name="Rakesh Menon", budget_min=5_000_000, budget_max=15_000_000,
                      notes=["Budget moved from 50 L to 1.5 Cr across two messages",
                             "Undecided between apartment and plot"]),
        "score": 35, "tier": "NEEDS_CLARIFICATION", "status": "NEEDS_INFORMATION",
        "action": "ASK_MORE_INFO",
        "next_step": "Ask the buyer to fix one budget band and one property type before matching.",
        "reasoning": ["Stated budget varies threefold between turns",
                      "Property type flips between apartment and plot",
                      "Matching across that range returns 30+ unfiltered results"],
        "turns": [("buyer", "I am looking at flats around 50 lakh."),
                  ("buyer", "Actually maybe 1.5 crore is fine. Or a plot. Not sure yet."),
                  ("agent", "Asked the buyer to settle on one budget band and property type.")],
    },
    {
        "lead_id": "L014", "name": "Shreya Anand", "contact": "shreya.a@example.com", "days_ago": 16.0,
        "inquiry": "Semi furnished 2BHK in Pattom around 60-65 lakh, planning next year sometime.",
        "reqs": _reqs(name="Shreya Anand", budget_min=6_000_000, budget_max=6_500_000,
                      locations=["Pattom"], property_type="Apartment", bhk=2,
                      timeline_months=12, timeline_text="next year",
                      furnishing="Semi-Furnished", purpose="SELF_USE"),
        "score": 52, "tier": "MEDIUM", "status": "NURTURING",
        "action": "NURTURE_LEAD",
        "next_step": "Quarterly check-in; revisit when the timeline moves inside six months.",
        "reasoning": ["Requirements are specific and inventory exists at P027",
                      "Twelve-month horizon does not justify broker time now",
                      "No financing conversation has started"],
        "turns": [("buyer", "Semi furnished 2BHK in Pattom around 60-65 lakh, planning next year sometime."),
                  ("agent", "Nurture track with a quarterly check-in.")],
    },
    {
        "lead_id": "L015", "name": "Joseph Mathew", "contact": "joseph.m@example.com", "days_ago": 3.5,
        "inquiry": "Plot of 5 cent in Sreekaryam or Peroorkada under 55 lakh, want to register within a month. "
                   "Funds ready.",
        "reqs": _reqs(name="Joseph Mathew", budget_max=5_500_000,
                      locations=["Sreekaryam", "Peroorkada"], property_type="Plot",
                      timeline_months=1, timeline_text="within a month",
                      financing_method="Own funds", financing_readiness="APPROVED",
                      purpose="INVESTMENT", viewing_ready=True),
        "score": 88, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Broker to arrange site visits for P016 and P042 this week.",
        "reasoning": ["Funds are ready and registration is targeted within a month",
                      "Two plots match both area and budget",
                      "Investment intent with a clear execution date"],
        "turns": [("buyer", "Plot of 5 cent in Sreekaryam or Peroorkada under 55 lakh, "
                            "want to register within a month. Funds ready."),
                  ("agent", "Escalated with two matching plots for immediate site visits.")],
    },
    {
        "lead_id": "L016", "name": "Aswathy Nair", "contact": None, "days_ago": 20.0,
        "inquiry": "Send me your best offers.",
        "reqs": _reqs(name="Aswathy Nair"),
        "score": 8, "tier": "LOW", "status": "LOW_PRIORITY",
        "action": "LOW_PRIORITY_OR_DISCARD",
        "next_step": "Leave in the low-priority bucket; re-engage only if the buyer replies with specifics.",
        "reasoning": ["No budget, area, configuration or timeline",
                      "Two clarification attempts went unanswered",
                      "Nothing to match against"],
        "turns": [("buyer", "Send me your best offers."),
                  ("agent", "Asked for budget and area - no reply received.")],
    },
    {
        "lead_id": "L017", "name": "Gopika S", "contact": "gopika.s@example.com", "days_ago": 6.5,
        "inquiry": "3BHK in Akkulam with lake view, up to 85 lakh, in about 5 months. "
                   "Waiting on loan eligibility.",
        "reqs": _reqs(name="Gopika S", budget_max=8_500_000, locations=["Akkulam"],
                      property_type="Apartment", bhk=3, timeline_months=5,
                      timeline_text="about 5 months", financing_method="Home loan",
                      financing_readiness="NOT_STARTED", parking_required=True,
                      purpose="SELF_USE"),
        "score": 66, "tier": "MEDIUM", "status": "QUALIFYING",
        "action": "SHOW_MATCHING_PROPERTIES",
        "next_step": "Share P018 and P021 and ask the buyer to start the loan eligibility check.",
        "reasoning": ["Location and configuration match two Akkulam listings",
                      "Five-month timeline is workable but financing has not begun",
                      "Buyer has not yet committed to a viewing"],
        "turns": [("buyer", "3BHK in Akkulam with lake view, up to 85 lakh, in about 5 months. "
                            "Waiting on loan eligibility."),
                  ("agent", "Shared two Akkulam matches and prompted the loan check.")],
    },
    {
        "lead_id": "L018", "name": "Hari Sankar", "contact": "hari.s@example.com", "days_ago": 18.0,
        "inquiry": "Want a villa in Kowdiar for 60 lakh.",
        "reqs": _reqs(name="Hari Sankar", budget_max=6_000_000, locations=["Kowdiar"],
                      property_type="Villa", purpose="SELF_USE"),
        "score": 20, "tier": "LOW", "status": "LOW_PRIORITY",
        "action": "RESET_EXPECTATIONS",
        "next_step": "Send the villa price-reality note with Peroorkada and Poojappura alternatives.",
        "reasoning": ["Only Kowdiar villa is listed at Rs 3.2 Cr",
                      "Cheapest villa anywhere in inventory is Rs 1.05 Cr",
                      "Budget gap is too large to bridge with negotiation"],
        "turns": [("buyer", "Want a villa in Kowdiar for 60 lakh."),
                  ("agent", "Explained the villa price floor and suggested other areas.")],
    },
    {
        "lead_id": "L019", "name": "Nazia Beevi", "contact": "nazia.b@example.com", "days_ago": 1.5,
        "inquiry": "Family of five, need 3BHK with play area and gym, Kesavadasapuram or Pattom, "
                   "65-75 lakh, shifting before school reopens in 4 months.",
        "reqs": _reqs(name="Nazia Beevi", budget_min=6_500_000, budget_max=7_500_000,
                      locations=["Kesavadasapuram", "Pattom"], property_type="Apartment", bhk=3,
                      timeline_months=4, timeline_text="before school reopens",
                      financing_method="Home loan", financing_readiness="IN_PROGRESS",
                      amenities=["Children Play Area", "Gym"], parking_required=True,
                      purpose="SELF_USE", viewing_ready=True),
        "score": 80, "tier": "HIGH", "status": "BROKER_ESCALATION",
        "action": "ESCALATE_TO_BROKER",
        "next_step": "Broker to present P044 and arrange a weekend family visit.",
        "reasoning": ["School deadline gives a hard four-month timeline",
                      "P044 satisfies budget, area, amenities and parking",
                      "Loan application already submitted"],
        "turns": [("buyer", "Family of five, need 3BHK with play area and gym, Kesavadasapuram or Pattom, "
                            "65-75 lakh, shifting before school reopens in 4 months."),
                  ("agent", "Escalated with one exact amenity match in Kesavadasapuram.")],
    },
    {
        "lead_id": "L020", "name": "Vivek Chandran", "contact": "vivek.c@example.com", "days_ago": 22.0,
        "inquiry": "Interested in Poojappura area, 3BHK, budget flexible, no rush at all.",
        "reqs": _reqs(name="Vivek Chandran", locations=["Poojappura"], bhk=3,
                      property_type="Apartment", timeline_text="no rush",
                      notes=["Budget described only as flexible"]),
        "score": 38, "tier": "NEEDS_CLARIFICATION", "status": "NEEDS_INFORMATION",
        "action": "ASK_MORE_INFO",
        "next_step": "Ask for a workable budget ceiling and any target date.",
        "reasoning": ["Area and configuration are clear, budget is not",
                      "Flexible budget spans Rs 66 L to Rs 1.42 Cr in Poojappura",
                      "Explicit lack of urgency"],
        "turns": [("buyer", "Interested in Poojappura area, 3BHK, budget flexible, no rush at all."),
                  ("agent", "Asked for a budget ceiling and a target date.")],
    },
]


def seed_leads() -> int:
    """Insert the historical leads, their conversations and one archived decision each."""
    for lead in SEED_LEADS:
        created = _ts(lead["days_ago"])
        db.create_lead(
            lead_id=lead["lead_id"],
            name=lead["name"],
            contact=lead["contact"],
            original_inquiry=lead["inquiry"],
            requirements=dict(lead["reqs"], original_inquiry=lead["inquiry"]),
            status=lead["status"],
            created_at=created,
        )
        db.update_lead(
            lead["lead_id"],
            intent_score=lead["score"],
            intent_tier=lead["tier"],
            status=lead["status"],
            current_action=lead["action"],
            recommended_next_step=lead["next_step"],
            summary={
                "reasoning": lead["reasoning"],
                "seeded": True,
            },
        )
        for offset, (role, message) in enumerate(lead["turns"]):
            db.add_turn(lead["lead_id"], role, message,
                        created_at=_ts(lead["days_ago"] - offset * 0.01))
        db.record_action(
            lead_id=lead["lead_id"],
            decision=lead["action"],
            intent_score=lead["score"],
            intent_tier=lead["tier"],
            reasoning=lead["reasoning"],
            input_snapshot={"requirements": lead["reqs"], "source": "seed"},
            output_snapshot={
                "decision": lead["action"],
                "recommended_next_step": lead["next_step"],
                "intent_score": lead["score"],
                "intent_tier": lead["tier"],
            },
            status_before="NEW",
            status_after=lead["status"],
            llm_provider="seed",
            timestamp=created,
        )
    return len(SEED_LEADS)
