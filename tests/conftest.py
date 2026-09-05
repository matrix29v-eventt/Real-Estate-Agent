"""Shared fixtures: an isolated database and a scripted LLM provider."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the application at a throwaway SQLite file and seed it."""
    monkeypatch.setenv("REALESTATE_DB", str(tmp_path / "test.db"))
    from services import db

    db.reset_db()
    db.ensure_seeded()
    return db


class ScriptedProvider:
    """A deterministic stand-in for a real model.

    Tests must never depend on a live LLM. This provider returns pre-scripted
    JSON payloads in order and records what it was asked, so the pipeline
    plumbing can be verified exactly.
    """

    name = "scripted"
    model = "test"

    def __init__(self, payloads: List[Dict[str, Any]]):
        self.payloads = list(payloads)
        self.calls: List[Dict[str, Any]] = []

    def available(self):
        return True, "scripted"

    def label(self) -> str:
        return f"{self.name}:{self.model}"

    def complete_json(self, system, user, schema, max_tokens=4000, effort="medium"):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self.payloads:
            raise AssertionError("ScriptedProvider ran out of payloads")
        return self.payloads.pop(0)


def extraction_payload(**overrides) -> Dict[str, Any]:
    base = {
        "name": None, "contact": None, "budget_min": None, "budget_max": None,
        "locations": [], "property_type": None, "bhk": None, "min_sqft": None,
        "timeline_months": None, "timeline_text": None, "financing_method": None,
        "financing_readiness": "UNKNOWN", "amenities": [], "parking_required": None,
        "furnishing": None, "purpose": "UNKNOWN", "viewing_ready": None, "notes": [],
    }
    base.update(overrides)
    return base


def decision_payload(**overrides) -> Dict[str, Any]:
    base = {
        "intent_score": 70,
        "intent_tier": "MEDIUM",
        "decision": "SHOW_MATCHING_PROPERTIES",
        "reasoning": ["Budget is clear", "Two matches exist in the requested area"],
        "missing_information": [],
        "risks": [],
        "recommended_next_step": "Share the shortlist and confirm the timeline.",
        "follow_up_question": None,
        "summary_headline": "Warm buyer with a clear budget",
        "confidence": 0.7,
        "draft_message": None,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def scripted():
    return ScriptedProvider
