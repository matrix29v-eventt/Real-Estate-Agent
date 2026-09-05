"""Deterministic buyer-intent signals.

This module computes *evidence*, not decisions. It answers factual questions -
what is missing, how complete is the picture, has the buyer contradicted
themselves, does affordable inventory exist, how does this lead compare on a
transparent scoring rubric - and hands all of it to the reasoning stage.

The heuristic score here is explicitly **an input to the agent, never a
threshold that selects the business action**. Two leads with the same score
routinely receive different next actions because the surrounding context differs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.schemas import (
    EvidencePack,
    FinancingReadiness,
    LeadRequirements,
    PropertyMatch,
    money,
)
from services import matcher

# Transparent rubric. Every component is explainable to a broker.
SCORE_WEIGHTS = {
    "budget_clarity": 20,
    "location_specificity": 15,
    "timeline_urgency": 20,
    "financing_readiness": 15,
    "requirement_specificity": 10,
    "inventory_support": 15,
    "viewing_readiness": 5,
}

CITYWIDE_TERMS = {"trivandrum", "thiruvananthapuram", "tvm", "kerala", "city", "anywhere"}

CRITICAL_FIELD_LABELS = {
    "budget": "Budget range",
    "locations": "Preferred location(s)",
    "timeline": "Purchase timeline",
}

SECONDARY_FIELD_LABELS = {
    "bhk": "Bedrooms / BHK",
    "property_type": "Property type",
    "financing_readiness": "Financing readiness",
    "purpose": "Purpose (self-use or investment)",
    "parking_required": "Parking requirement",
    "furnishing": "Furnishing preference",
    "amenities": "Desired amenities",
    "contact": "Contact details",
    "viewing_ready": "Willingness to view",
}


# --------------------------------------------------------------------------- #
# Missing-information analysis
# --------------------------------------------------------------------------- #
def has_budget(req: LeadRequirements) -> bool:
    return req.budget_min is not None or req.budget_max is not None


def has_specific_location(req: LeadRequirements) -> bool:
    return any(loc.strip().lower() not in CITYWIDE_TERMS for loc in req.locations if loc.strip())


def has_timeline(req: LeadRequirements) -> bool:
    return req.timeline_months is not None or bool(req.timeline_text)


def missing_fields(req: LeadRequirements) -> tuple[List[str], List[str]]:
    critical: List[str] = []
    if not has_budget(req):
        critical.append(CRITICAL_FIELD_LABELS["budget"])
    if not has_specific_location(req):
        critical.append(CRITICAL_FIELD_LABELS["locations"])
    if not has_timeline(req):
        critical.append(CRITICAL_FIELD_LABELS["timeline"])

    present = {
        "bhk": req.bhk is not None,
        "property_type": bool(req.property_type),
        "financing_readiness": req.financing_readiness != FinancingReadiness.UNKNOWN,
        "purpose": req.purpose.value != "UNKNOWN",
        "parking_required": req.parking_required is not None,
        "furnishing": bool(req.furnishing),
        "amenities": bool(req.amenities),
        "contact": bool(req.contact),
        "viewing_ready": req.viewing_ready is not None,
    }
    secondary = [SECONDARY_FIELD_LABELS[k] for k, ok in present.items() if not ok]
    return critical, secondary


def completeness_pct(req: LeadRequirements) -> int:
    critical_present = sum(
        [has_budget(req), has_specific_location(req), has_timeline(req)]
    )
    _, secondary_missing = missing_fields(req)
    secondary_total = len(SECONDARY_FIELD_LABELS)
    secondary_present = secondary_total - len(secondary_missing)
    # Critical fields carry two-thirds of the weight.
    score = (critical_present / 3) * 0.67 + (secondary_present / secondary_total) * 0.33
    return int(round(score * 100))


# --------------------------------------------------------------------------- #
# Contradiction detection across conversation turns
# --------------------------------------------------------------------------- #
def detect_contradictions(
    current: LeadRequirements, previous: Optional[Dict[str, Any]]
) -> List[str]:
    """Compare the merged state against the previous snapshot.

    Buyers legitimately *add* information; that is not a contradiction. A
    contradiction is a value that moved materially, which is a real signal about
    how firm the buyer's requirements are.
    """
    if not previous:
        return []
    notes: List[str] = []
    prev = LeadRequirements(**previous) if not isinstance(previous, LeadRequirements) else previous

    old_ceiling = prev.budget_max or prev.budget_min
    new_ceiling = current.budget_max or current.budget_min
    if old_ceiling and new_ceiling:
        ratio = max(old_ceiling, new_ceiling) / min(old_ceiling, new_ceiling)
        if ratio >= 1.5:
            notes.append(
                f"Budget moved from {money(old_ceiling)} to {money(new_ceiling)} between turns"
            )

    old_locs = {l.lower() for l in prev.locations}
    new_locs = {l.lower() for l in current.locations}
    if old_locs and new_locs and not (old_locs & new_locs):
        notes.append(
            f"Preferred areas changed completely ({', '.join(sorted(old_locs))} -> "
            f"{', '.join(sorted(new_locs))})"
        )

    if prev.bhk and current.bhk and prev.bhk != current.bhk:
        notes.append(f"Configuration changed from {prev.bhk} BHK to {current.bhk} BHK")

    if prev.property_type and current.property_type and (
        prev.property_type.lower() != current.property_type.lower()
    ):
        notes.append(
            f"Property type changed from {prev.property_type} to {current.property_type}"
        )

    if prev.timeline_months is not None and current.timeline_months is not None:
        if abs(prev.timeline_months - current.timeline_months) >= 6:
            notes.append(
                f"Timeline moved from ~{prev.timeline_months:.0f} to "
                f"~{current.timeline_months:.0f} months"
            )
    return notes


# --------------------------------------------------------------------------- #
# Heuristic score
# --------------------------------------------------------------------------- #
def _timeline_points(req: LeadRequirements) -> int:
    months = req.timeline_months
    if months is None:
        return 4 if req.timeline_text else 0
    if months <= 3:
        return 20
    if months <= 6:
        return 14
    if months <= 12:
        return 8
    return 3


def _financing_points(req: LeadRequirements) -> int:
    return {
        FinancingReadiness.APPROVED: 15,
        FinancingReadiness.IN_PROGRESS: 10,
        FinancingReadiness.NOT_STARTED: 4,
        FinancingReadiness.UNKNOWN: 0,
    }[req.financing_readiness]


def _specificity_points(req: LeadRequirements) -> int:
    filled = sum(
        1
        for value in (
            req.bhk,
            req.property_type,
            req.min_sqft,
            req.furnishing,
            req.parking_required,
            req.amenities or None,
        )
        if value is not None
    )
    return min(10, round(filled * 10 / 6))


def matching_is_meaningful(req: LeadRequirements) -> bool:
    """Matching only carries weight once the buyer has narrowed something down.

    Scoring the whole catalogue against "a nice flat in Trivandrum" produces
    high percentages that mean nothing, so the evidence pack says so explicitly.
    """
    anchors = [has_budget(req), has_specific_location(req),
               req.bhk is not None or bool(req.property_type)]
    return sum(anchors) >= 2 and has_budget(req)


def _inventory_points(matches: List[PropertyMatch], req: LeadRequirements) -> int:
    if not matching_is_meaningful(req):
        # Cannot claim inventory support for requirements this loose.
        return 2 if matches else 0
    strong = [m for m in matches if m.match_pct >= matcher.STRONG_MATCH_THRESHOLD]
    if not matches:
        return 0
    if len(strong) >= 3:
        return 15
    if len(strong) == 2:
        return 12
    if len(strong) == 1:
        return 9
    return 4 if matches[0].match_pct >= 55 else 1


def compute_evidence(
    req: LeadRequirements,
    matches: List[PropertyMatch],
    properties: List[Dict[str, Any]],
    previous_requirements: Optional[Dict[str, Any]] = None,
    conversation_turns: int = 1,
) -> EvidencePack:
    """Build the full deterministic evidence pack for one agent turn."""
    critical_missing, secondary_missing = missing_fields(req)

    breakdown = {
        "budget_clarity": 20 if (req.budget_min and req.budget_max)
        else (15 if has_budget(req) else 0),
        "location_specificity": 15 if has_specific_location(req)
        else (6 if req.locations else 0),
        "timeline_urgency": _timeline_points(req),
        "financing_readiness": _financing_points(req),
        "requirement_specificity": _specificity_points(req),
        "inventory_support": _inventory_points(matches, req),
        "viewing_readiness": 5 if req.viewing_ready else 0,
    }

    realism = matcher.budget_realism(req, properties)
    contradictions = detect_contradictions(req, previous_requirements)

    penalties: Dict[str, int] = {}
    if realism.get("verdict") == "UNREALISTIC":
        penalties["unrealistic_budget"] = -25
    elif realism.get("verdict") == "TIGHT":
        penalties["tight_budget"] = -8
    if contradictions:
        penalties["contradictions"] = -min(16, 8 * len(contradictions))
    if conversation_turns >= 3 and critical_missing:
        penalties["still_vague_after_clarification"] = -10

    breakdown.update(penalties)
    raw = sum(breakdown.values())
    score = max(0, min(100, raw))

    strong = [m for m in matches if m.match_pct >= matcher.STRONG_MATCH_THRESHOLD]
    meaningful = matching_is_meaningful(req)
    inventory = matcher.inventory_stats(req, properties)
    inventory["matching_is_meaningful"] = meaningful
    if not meaningful:
        inventory["note"] = (
            "Requirements are too loose for property matching to be informative; "
            "match percentages below should not be treated as evidence of fit."
        )

    return EvidencePack(
        completeness_pct=completeness_pct(req),
        missing_critical_fields=critical_missing,
        missing_secondary_fields=secondary_missing,
        heuristic_score=score,
        score_breakdown=breakdown,
        budget_realism=realism,
        inventory_stats=inventory,
        contradictions=contradictions,
        conversation_turns=conversation_turns,
        top_match_pct=matches[0].match_pct if matches else 0,
        strong_match_count=len(strong) if meaningful else 0,
    )
