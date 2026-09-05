"""Deterministic property matching.

This module contains **no LLM calls**. It answers a mechanical question -
"how compatible is this listing with what the buyer said?" - and produces a
compatibility percentage plus human-readable reasons and gaps.

A weighted calculation is appropriate here precisely because this is *not* the
business decision: the score and its explanation become evidence that the
reasoning stage weighs alongside everything else.

Criteria the buyer has not specified are skipped and their weight is removed
from the denominator, so a vague inquiry is not silently penalised - the
missing-information analysis in ``signals.py`` handles that instead.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import config
from models.schemas import LeadRequirements, PropertyMatch, money

WEIGHTS = {
    "location": 25,
    "budget": 25,
    "bhk": 15,
    "property_type": 10,
    "timeline": 10,
    "parking": 5,
    "furnishing": 5,
    "amenities": 5,
}

# A listing scoring at or above this is treated as a "strong" match.
STRONG_MATCH_THRESHOLD = 75


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def _location_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    wanted = [_norm(loc) for loc in req.locations if _norm(loc)]
    if not wanted:
        return -1.0, ""
    actual = _norm(prop["location"])
    if actual in wanted:
        return 1.0, f"Exact location match ({prop['location']})"
    # City-wide phrasing ("anywhere in Trivandrum") should not zero the criterion.
    citywide = {"trivandrum", "thiruvananthapuram", "tvm", "city"}
    if any(w in citywide for w in wanted):
        return 0.7, f"Inside the requested city area ({prop['location']})"
    for want in wanted:
        neighbours = [_norm(n) for n in config.LOCATION_NEIGHBOURS.get(want, [])]
        if actual in neighbours:
            return 0.6, f"Adjacent to preferred area ({prop['location']} near {want.title()})"
    return 0.0, ""


def _budget_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    low, high = req.budget_min, req.budget_max
    if low is None and high is None:
        return -1.0, ""
    price = int(prop["price"])
    if low is not None and high is not None:
        if low <= price <= high:
            return 1.0, f"Priced inside budget at {money(price)}"
        reference = high if price > high else low
    else:
        reference = high if high is not None else low
        if (high is not None and price <= high) or (low is not None and price >= low):
            return 1.0, f"Priced inside budget at {money(price)}"
    drift = abs(price - reference) / max(reference, 1)
    if drift <= 0.10:
        return 0.6, f"Within 10% of budget at {money(price)}"
    if drift <= 0.25:
        return 0.25, f"Stretches budget by {drift * 100:.0f}% at {money(price)}"
    return 0.0, ""


def _bhk_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    if req.bhk is None:
        return -1.0, ""
    prop_bhk = prop.get("bhk")
    if prop_bhk is None:
        # Plots have no BHK; neutral rather than a penalty.
        return -1.0, ""
    if prop_bhk == req.bhk:
        return 1.0, f"{prop_bhk} BHK as requested"
    if abs(prop_bhk - req.bhk) == 1:
        return 0.4, f"{prop_bhk} BHK against a {req.bhk} BHK request"
    return 0.0, ""


def _type_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    if not req.property_type:
        return -1.0, ""
    if _norm(req.property_type) == _norm(prop["property_type"]):
        return 1.0, f"{prop['property_type']} as requested"
    return 0.0, ""


def _timeline_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    if req.timeline_months is None:
        return -1.0, ""
    ready = _norm(prop.get("possession_status")) == "ready to move"
    if ready:
        return 1.0, "Ready to move, fits the stated timeline"
    months_to_possession = _months_until(prop.get("possession_date"))
    if months_to_possession is None:
        return 0.3, "Possession date not confirmed"
    if months_to_possession <= req.timeline_months:
        return 0.9, f"Possession in ~{months_to_possession} months, inside the buyer window"
    return 0.0, ""


def _parking_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    if req.parking_required is None:
        return -1.0, ""
    if not req.parking_required:
        return 1.0, ""
    return (1.0, "Parking available") if prop.get("parking") else (0.0, "")


def _furnishing_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    if not req.furnishing:
        return -1.0, ""
    order = {f.lower(): i for i, f in enumerate(config.FURNISHING_OPTIONS)}
    want = order.get(_norm(req.furnishing))
    have = order.get(_norm(prop.get("furnishing")))
    if want is None or have is None:
        return -1.0, ""
    if want == have:
        return 1.0, f"{prop['furnishing']} as requested"
    if have > want:
        return 0.8, f"Better furnished than requested ({prop['furnishing']})"
    return 0.2, ""


def _amenity_score(req: LeadRequirements, prop: Dict[str, Any]) -> tuple[float, str]:
    wanted = [_norm(a) for a in req.amenities if _norm(a)]
    if not wanted:
        return -1.0, ""
    have = {_norm(a) for a in prop.get("amenities", [])}
    have |= {_norm(t).replace("-", " ") for t in prop.get("tags", [])}
    hits = [a for a in wanted if any(a in h or h in a for h in have)]
    if not hits:
        return 0.0, ""
    ratio = len(hits) / len(wanted)
    label = ", ".join(h.title() for h in hits)
    return ratio, f"Has {label}"


_SCORERS = {
    "location": _location_score,
    "budget": _budget_score,
    "bhk": _bhk_score,
    "property_type": _type_score,
    "timeline": _timeline_score,
    "parking": _parking_score,
    "furnishing": _furnishing_score,
    "amenities": _amenity_score,
}

_GAP_LABELS = {
    "location": "Not in a preferred area",
    "budget": "Outside the stated budget",
    "bhk": "Different configuration",
    "property_type": "Different property type",
    "timeline": "Possession later than the buyer window",
    "parking": "No parking",
    "furnishing": "Furnishing below preference",
    "amenities": "Missing the requested amenities",
}


def _months_until(possession_date: Optional[str], today: Optional[date] = None) -> Optional[int]:
    if not possession_date:
        return None
    try:
        target = datetime.fromisoformat(str(possession_date)).date()
    except ValueError:
        return None
    today = today or date.today()
    return max(0, round((target - today).days / 30.44))


def score_property(req: LeadRequirements, prop: Dict[str, Any]) -> PropertyMatch:
    """Score one listing against the buyer requirements."""
    earned = 0.0
    possible = 0.0
    reasons: List[str] = []
    gaps: List[str] = []
    out_of_budget = False

    for key, weight in WEIGHTS.items():
        ratio, note = _SCORERS[key](req, prop)
        if ratio < 0:  # criterion not specified by the buyer
            continue
        possible += weight
        earned += weight * ratio
        if note:
            reasons.append(note)
        elif ratio < 0.5:
            gaps.append(_GAP_LABELS[key])
            if key == "budget" and ratio == 0.0:
                out_of_budget = True

    pct = int(round(100 * earned / possible)) if possible else 0

    if out_of_budget:
        # A listing the buyer cannot afford is never a strong match, however
        # well it scores on everything else. It stays visible (the agent needs
        # to see the closest real inventory) but capped well below "strong".
        pct = min(pct, 45)

    availability = str(prop.get("availability", "AVAILABLE"))
    if availability != "AVAILABLE":
        # Unavailable stock is never presented as a real option.
        pct = min(pct, 25)
        gaps.insert(0, f"Currently {availability.replace('_', ' ').lower()}")

    if not reasons and pct >= 50:
        reasons.append("Broadly consistent with the stated requirements")

    return PropertyMatch(
        property_id=prop["property_id"],
        name=prop["name"],
        location=prop["location"],
        property_type=prop["property_type"],
        bhk=prop.get("bhk"),
        price=int(prop["price"]),
        sqft=int(prop["sqft"]),
        availability=availability,
        match_pct=pct,
        reasons=reasons[:5],
        gaps=gaps[:4],
        tags=list(prop.get("tags", [])),
    )


def match_properties(
    req: LeadRequirements,
    properties: List[Dict[str, Any]],
    limit: int = 5,
    min_pct: int = 35,
) -> List[PropertyMatch]:
    """Return the best listings for a buyer, best first.

    Listings that are not genuinely relevant are dropped rather than padded -
    the agent must be able to see when inventory simply does not exist.
    """
    scored = [score_property(req, prop) for prop in properties]
    scored.sort(key=lambda m: (m.match_pct, -m.price), reverse=True)
    kept = [m for m in scored if m.match_pct >= min_pct and m.availability == "AVAILABLE"]
    return kept[:limit]


def inventory_stats(req: LeadRequirements, properties: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Facts about what inventory actually exists for this buyer's constraints.

    Used as evidence for budget-realism reasoning: "the cheapest 4BHK in Kowdiar
    is Rs 2.45 Cr" is a far stronger input than a bare compatibility score.
    """
    available = [p for p in properties if p.get("availability") == "AVAILABLE"]
    wanted_locations = {_norm(loc) for loc in req.locations if _norm(loc)}

    in_area = [p for p in available if _norm(p["location"]) in wanted_locations] if wanted_locations else available
    in_area_and_config = [
        p for p in in_area
        if (req.bhk is None or p.get("bhk") == req.bhk)
        and (not req.property_type or _norm(p["property_type"]) == _norm(req.property_type))
    ]

    stats: Dict[str, Any] = {
        "total_available": len(available),
        "in_requested_areas": len(in_area),
        "matching_area_and_configuration": len(in_area_and_config),
    }
    if in_area:
        stats["cheapest_in_requested_areas"] = min(p["price"] for p in in_area)
        stats["cheapest_in_requested_areas_label"] = money(stats["cheapest_in_requested_areas"])
    if in_area_and_config:
        prices = [p["price"] for p in in_area_and_config]
        stats["cheapest_matching_configuration"] = min(prices)
        stats["cheapest_matching_configuration_label"] = money(min(prices))
        stats["median_matching_configuration_label"] = money(sorted(prices)[len(prices) // 2])
    return stats


def budget_realism(req: LeadRequirements, properties: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare the buyer's ceiling against the real price floor for what they asked for."""
    stats = inventory_stats(req, properties)
    ceiling = req.budget_max or req.budget_min
    result: Dict[str, Any] = {
        "buyer_ceiling": ceiling,
        "buyer_ceiling_label": money(ceiling) if ceiling else None,
        "verdict": "UNKNOWN",
    }
    floor = stats.get("cheapest_matching_configuration") or stats.get("cheapest_in_requested_areas")
    if floor is None or ceiling is None:
        result["reason"] = "Budget or requirements are too incomplete to judge realism."
        return result

    result["market_floor"] = floor
    result["market_floor_label"] = money(floor)
    ratio = ceiling / floor
    result["ceiling_to_floor_ratio"] = round(ratio, 2)
    if ratio >= 1.0:
        result["verdict"] = "REALISTIC"
        result["reason"] = f"Budget clears the {money(floor)} entry price for these requirements."
    elif ratio >= 0.75:
        result["verdict"] = "TIGHT"
        result["reason"] = f"Budget is {(1 - ratio) * 100:.0f}% below the {money(floor)} entry price."
    else:
        result["verdict"] = "UNREALISTIC"
        result["reason"] = (
            f"Entry price for these requirements is {money(floor)}, "
            f"about {floor / max(ceiling, 1):.1f}x the stated budget."
        )
    return result
