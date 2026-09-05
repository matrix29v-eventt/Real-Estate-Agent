"""Render smoke tests for the Streamlit app.

These catch the class of bug that unit tests miss entirely: a view that raises
while rendering. `AppTest` executes the real script in-process, so every
`st.*` call in every view is exercised without a browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
VIEWS = ["New Lead / Conversation", "Lead Analysis", "Lead Dashboard"]


def _run(temp_db, **session) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    for key, value in session.items():
        app.session_state[key] = value
    app.run()
    return app


def test_app_starts_without_exceptions(temp_db):
    app = _run(temp_db)
    assert not app.exception
    assert "Real Estate Lead Qualification Agent" in app.title[0].value


def test_every_view_renders(temp_db):
    for view in VIEWS:
        app = _run(temp_db, active_view=view)
        assert not app.exception, f"{view} raised: {app.exception}"


def test_dashboard_shows_seeded_metrics(temp_db):
    app = _run(temp_db, active_view="Lead Dashboard")
    assert not app.exception
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Total leads"] == "20"
    assert int(metrics["Broker escalations"]) > 0
    assert int(metrics["Decisions logged"]) > 0


def test_analysis_view_renders_a_stored_lead(temp_db):
    app = _run(temp_db, active_view="Lead Analysis", active_lead_id="L001")
    assert not app.exception
    text = " ".join(m.value for m in app.markdown if isinstance(m.value, str))
    assert "Rahul Nair" in text or any("Rahul Nair" in str(c.value) for c in app.code)


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
