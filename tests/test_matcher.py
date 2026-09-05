"""Deterministic property matching and inventory diagnostics."""

from __future__ import annotations

import pytest

from models.schemas import LeadRequirements
from services import matcher


@pytest.fixture()
def props(temp_db):
    return temp_db.list_properties()


def test_exact_requirements_produce_strong_matches(props):
    req = LeadRequirements(
        budget_min=6_500_000, budget_max=7_500_000,
        locations=["Technopark", "Kazhakkoottam"],
        property_type="Apartment", bhk=3, timeline_months=2,
        parking_required=True, amenities=["Gated Community"],
    )
    matches = matcher.match_properties(req, props)
    assert len(matches) >= 3
    assert matches[0].match_pct >= 90
    assert all(m.match_pct >= matcher.STRONG_MATCH_THRESHOLD for m in matches[:3])
    assert any("Exact location match" in r for r in matches[0].reasons)
    # Sorted best-first.
    assert matches == sorted(matches, key=lambda m: m.match_pct, reverse=True)


def test_matches_stay_inside_budget(props):
    req = LeadRequirements(budget_max=6_000_000, locations=["Kazhakkoottam"], bhk=3)
    for match in matcher.match_properties(req, props):
        assert match.price <= 6_600_000  # at most the 10% tolerance band


def test_out_of_budget_listings_are_capped(props):
    """A property 10x over budget must never present as a strong match."""
    req = LeadRequirements(budget_max=2_500_000, locations=["Kowdiar"], bhk=4)
    matches = matcher.match_properties(req, props)
    assert all(m.match_pct <= 45 for m in matches)
    assert all("Outside the stated budget" in m.gaps for m in matches)


def test_unavailable_stock_is_never_offered(props):
    req = LeadRequirements(budget_max=7_000_000, locations=["Kazhakkoottam"],
                           property_type="Plot")
    ids = {m.property_id for m in matcher.match_properties(req, props)}
    assert "P007" not in ids  # sold out


def test_unspecified_criteria_do_not_penalise(props):
    """Only what the buyer actually said should count against a listing."""
    req = LeadRequirements(locations=["Pattom"], property_type="Apartment")
    matches = matcher.match_properties(req, props)
    assert matches and matches[0].match_pct == 100


def test_neighbouring_areas_are_recognised(props):
    req = LeadRequirements(budget_max=7_500_000, locations=["Technopark"], bhk=3,
                           property_type="Apartment")
    matches = matcher.match_properties(req, props)
    adjacent = [m for m in matches if m.location != "Technopark"]
    assert adjacent, "expected nearby areas to surface too"
    assert all(m.match_pct < 100 for m in adjacent)


def test_budget_realism_verdicts(props):
    realistic = LeadRequirements(budget_max=7_500_000, locations=["Kazhakkoottam"],
                                 bhk=3, property_type="Apartment")
    assert matcher.budget_realism(realistic, props)["verdict"] == "REALISTIC"

    impossible = LeadRequirements(budget_max=2_500_000, locations=["Kowdiar"],
                                  bhk=4, property_type="Apartment")
    verdict = matcher.budget_realism(impossible, props)
    assert verdict["verdict"] == "UNREALISTIC"
    assert verdict["market_floor"] > 20_000_000

    unknown = LeadRequirements(locations=["Kowdiar"])
    assert matcher.budget_realism(unknown, props)["verdict"] == "UNKNOWN"


def test_inventory_stats_report_real_counts(props):
    req = LeadRequirements(locations=["Kowdiar"], bhk=4, property_type="Apartment")
    stats = matcher.inventory_stats(req, props)
    assert stats["in_requested_areas"] == 5
    assert stats["matching_area_and_configuration"] == 1
    assert stats["cheapest_matching_configuration"] == 24_500_000
