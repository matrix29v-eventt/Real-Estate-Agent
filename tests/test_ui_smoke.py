"""Render smoke tests for the Streamlit app.

These catch the class of bug that unit tests miss entirely: a view that raises
while rendering. `AppTest` executes the real script in-process, so every
`st.*` call in every view is exercised without a browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

from services import auth

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BROKER_VIEWS = [
    "New Lead / Conversation", "Lead Analysis", "Lead Dashboard", "Property Inventory",
]

BROKER = auth.Account(username="priya", display_name="Priya", role=auth.BROKER)
BUYER = auth.Account(username="rahul-nair", display_name="Rahul Nair", role=auth.BUYER)


def _run(temp_db, account=BROKER, **session) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    if account is not None:
        app.session_state[auth.SESSION_KEY] = account
    for key, value in session.items():
        app.session_state[key] = value
    app.run()
    return app


def _text(app) -> str:
    parts = [m.value for m in app.markdown if isinstance(m.value, str)]
    parts += [c.value for c in app.code if isinstance(c.value, str)]
    parts += [c.value for c in app.caption if isinstance(c.value, str)]
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Sign-in gate
# --------------------------------------------------------------------------- #
def test_signed_out_users_see_the_login_page(temp_db):
    app = _run(temp_db, account=None)
    assert not app.exception
    text = _text(app)
    assert "Sign in" in " ".join(h.value for h in app.subheader)
    # No pipeline data leaks before signing in.
    assert "Lead Dashboard" not in text


def test_login_page_is_honest_about_what_it_is(temp_db):
    app = _run(temp_db, account=None)
    assert "not a security system" in _text(app).lower()


def test_buyer_sign_in_creates_an_account():
    account = auth.sign_in(auth.BUYER, "Rahul Nair")
    assert account.role == auth.BUYER
    assert account.username == "rahul-nair"
    assert not account.is_broker


def test_broker_sign_in_requires_the_code():
    with pytest.raises(auth.SignInError):
        auth.sign_in(auth.BROKER, "Priya", "wrong-code")
    account = auth.sign_in(auth.BROKER, "Priya", auth.broker_access_code())
    assert account.is_broker


def test_buyer_names_are_validated():
    for bad in ("", " ", "x", "!!!"):
        with pytest.raises(auth.SignInError):
            auth.sign_in(auth.BUYER, bad)


def test_same_name_returns_to_the_same_account():
    assert (auth.sign_in(auth.BUYER, "Rahul Nair").username
            == auth.sign_in(auth.BUYER, "  rahul   nair ").username)


# --------------------------------------------------------------------------- #
# Broker experience
# --------------------------------------------------------------------------- #
def test_app_starts_without_exceptions(temp_db):
    app = _run(temp_db)
    assert not app.exception
    assert "Real Estate Lead Qualification Agent" in app.title[0].value


def test_every_broker_view_renders(temp_db):
    for view in BROKER_VIEWS:
        app = _run(temp_db, active_view=view)
        assert not app.exception, f"{view} raised: {app.exception}"


def test_dashboard_shows_seeded_metrics(temp_db):
    app = _run(temp_db, active_view="Lead Dashboard")
    assert not app.exception
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Total leads"] == "20"
    assert int(metrics["Broker escalations"]) > 0
    assert int(metrics["Decisions logged"]) > 0


def test_property_inventory_lists_the_catalogue(temp_db):
    app = _run(temp_db, active_view="Property Inventory")
    assert not app.exception
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Total listings"] == "53"
    assert int(metrics["Available"]) < 53  # sold-out stock is excluded


def test_analysis_view_renders_a_stored_lead(temp_db):
    app = _run(temp_db, active_view="Lead Analysis", active_lead_id="L001")
    assert not app.exception
    assert "Rahul Nair" in _text(app)


def test_analysis_view_handles_no_active_lead(temp_db):
    app = _run(temp_db, active_view="Lead Analysis", active_lead_id=None)
    assert not app.exception
    assert any("Analyse an inquiry" in i.value for i in app.info)


@pytest.mark.parametrize("lead_id", ["L003", "L004", "L005", "L016"])
def test_analysis_renders_every_lead_archetype(temp_db, lead_id):
    """Vague, unrealistic, long-term and dead leads must all render."""
    app = _run(temp_db, active_view="Lead Analysis", active_lead_id=lead_id)
    assert not app.exception, f"{lead_id} raised: {app.exception}"


def test_missing_llm_is_reported_not_faked(temp_db, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    app = _run(temp_db)
    assert not app.exception
    errors = " ".join(e.value for e in app.error)
    assert "No LLM configured" in errors


# --------------------------------------------------------------------------- #
# Buyer experience
# --------------------------------------------------------------------------- #
def test_buyer_portal_renders(temp_db):
    app = _run(temp_db, account=BUYER)
    assert not app.exception
    assert "Rahul Nair" in _text(app) or any(
        "Rahul Nair" in c.value for c in app.caption
    )


def test_buyer_sees_only_their_own_enquiries(temp_db):
    """A buyer must not see the 20 seeded leads, which belong to nobody."""
    temp_db.create_lead(lead_id="L900", name="Rahul Nair",
                        original_inquiry="3BHK near Technopark", owner="rahul-nair")
    temp_db.create_lead(lead_id="L901", name="Someone Else",
                        original_inquiry="2BHK in Pattom", owner="someone-else")

    app = _run(temp_db, account=BUYER, buyer_view="My enquiries")
    assert not app.exception
    labels = " ".join(e.label for e in app.expander)
    assert "L900" in labels
    assert "L901" not in labels
    assert "L001" not in labels


def test_buyer_never_sees_broker_internals(temp_db):
    """Intent scores, rubric and escalation wording are broker-facing only."""
    temp_db.create_lead(lead_id="L900", name="Rahul Nair",
                        original_inquiry="3BHK near Technopark", owner="rahul-nair")
    app = _run(temp_db, account=BUYER, active_lead_id="L900")
    assert not app.exception
    text = _text(app).lower()
    for forbidden in ("heuristic", "intent score", "escalate_to_broker",
                      "low_priority_or_discard", "audit trail"):
        assert forbidden not in text, f"buyer view leaked {forbidden!r}"


def test_buyer_cannot_open_someone_elses_lead(temp_db):
    """A lead id in session state must not grant access to another buyer's lead."""
    app = _run(temp_db, account=BUYER, active_lead_id="L001")  # a seeded lead
    assert not app.exception
    assert "Escalate" not in _text(app)


def test_buyer_has_no_data_controls(temp_db):
    app = _run(temp_db, account=BUYER)
    labels = [b.label for b in app.button]
    assert "Reset demo data" not in labels
    assert "Sign out" in labels


# --------------------------------------------------------------------------- #
# Button clicks
#
# Rendering a view is not enough: a handler that writes to a widget's own key
# after that widget exists raises StreamlitWidgetAlreadyInstantiatedError, and
# only a real click reaches it. Every navigation button gets clicked here.
# --------------------------------------------------------------------------- #
def _click(app, label: str):
    for button in app.button:
        if button.label == label:
            return button.click().run()
    raise AssertionError(f"no button labelled {label!r}; saw {[b.label for b in app.button]}")


def test_buyer_can_open_an_enquiry_from_the_list(temp_db):
    temp_db.create_lead(lead_id="L900", name="Rahul Nair",
                        original_inquiry="3BHK near Technopark", owner="rahul-nair")
    app = _run(temp_db, account=BUYER, buyer_view="My enquiries")
    assert not app.exception

    app = _click(app, "Open this enquiry")
    assert not app.exception, f"opening an enquiry raised: {app.exception}"
    assert app.session_state["active_lead_id"] == "L900"
    assert app.session_state["buyer_view"] == "New enquiry"


def test_broker_can_open_a_lead_in_the_analysis_view(temp_db):
    app = _run(temp_db, active_view="Lead Dashboard")
    app = _click(app, "Open in Lead Analysis")
    assert not app.exception, f"opening a lead raised: {app.exception}"
    assert app.session_state["active_view"] == "Lead Analysis"


def test_broker_can_open_full_analysis_from_a_turn(temp_db):
    """The New Lead view offers a jump to the analysis once a turn has run."""
    from conftest import ScriptedProvider, decision_payload, extraction_payload
    from services import agent

    result = agent.run_turn(
        "2BHK in Pattom for 60 lakh",
        provider=ScriptedProvider([
            extraction_payload(budget_max=6_000_000, locations=["Pattom"], bhk=2),
            decision_payload(),
        ]),
    )
    app = _run(temp_db, active_view="New Lead / Conversation",
               active_lead_id=result.lead_id, last_result=result)
    app = _click(app, "Open full analysis")
    assert not app.exception, f"jumping to the analysis raised: {app.exception}"
    assert app.session_state["active_view"] == "Lead Analysis"


def test_sign_out_returns_to_the_login_page(temp_db):
    app = _run(temp_db, account=BUYER, buyer_view="My enquiries")
    app = _click(app, "Sign out")
    assert not app.exception, f"signing out raised: {app.exception}"
    assert auth.SESSION_KEY not in app.session_state
    assert "Sign in" in " ".join(h.value for h in app.subheader)


def test_broker_reset_demo_data_survives_a_click(temp_db):
    app = _run(temp_db, active_view="Lead Dashboard")
    app = _click(app, "Reset demo data")
    assert not app.exception, f"resetting raised: {app.exception}"
    assert temp_db.count_rows("leads") == 20


def test_starting_a_new_lead_clears_the_active_one(temp_db):
    app = _run(temp_db, active_view="New Lead / Conversation", active_lead_id="L001")
    app = _click(app, "Start a new lead")
    assert not app.exception
    assert app.session_state["active_lead_id"] is None
