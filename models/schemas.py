"""Structured contracts for everything that crosses the agent boundary.

Two of these models are *LLM output contracts* and are validated before any
result is trusted or persisted:

* LeadRequirements  - stage 1 (extraction / context merge)
* AgentDecision     - stage 2 (qualification + next-action reasoning)

The remaining models describe deterministic Python output (matches, evidence).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class IntentTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class NextAction(str, Enum):
    ASK_MORE_INFO = "ASK_MORE_INFO"
    SHOW_MATCHING_PROPERTIES = "SHOW_MATCHING_PROPERTIES"
    ESCALATE_TO_BROKER = "ESCALATE_TO_BROKER"
    NURTURE_LEAD = "NURTURE_LEAD"
    RESET_EXPECTATIONS = "RESET_EXPECTATIONS"
    LOW_PRIORITY_OR_DISCARD = "LOW_PRIORITY_OR_DISCARD"


class LeadStatus(str, Enum):
    NEW = "NEW"
    QUALIFYING = "QUALIFYING"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    QUALIFIED = "QUALIFIED"
    BROKER_ESCALATION = "BROKER_ESCALATION"
    NURTURING = "NURTURING"
    LOW_PRIORITY = "LOW_PRIORITY"


class Purpose(str, Enum):
    SELF_USE = "SELF_USE"
    INVESTMENT = "INVESTMENT"
    UNKNOWN = "UNKNOWN"


class FinancingReadiness(str, Enum):
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    NOT_STARTED = "NOT_STARTED"
    UNKNOWN = "UNKNOWN"


# Deterministic bookkeeping only: which lifecycle state a decision implies.
# This is NOT the business decision - the agent already made that.
ACTION_TO_STATUS: Dict[str, str] = {
    NextAction.ASK_MORE_INFO.value: LeadStatus.NEEDS_INFORMATION.value,
    NextAction.SHOW_MATCHING_PROPERTIES.value: LeadStatus.QUALIFYING.value,
    NextAction.ESCALATE_TO_BROKER.value: LeadStatus.BROKER_ESCALATION.value,
    NextAction.NURTURE_LEAD.value: LeadStatus.NURTURING.value,
    NextAction.RESET_EXPECTATIONS.value: LeadStatus.QUALIFYING.value,
    NextAction.LOW_PRIORITY_OR_DISCARD.value: LeadStatus.LOW_PRIORITY.value,
}


# --------------------------------------------------------------------------- #
# Stage 1 contract - extracted / merged buyer requirements
# --------------------------------------------------------------------------- #
class LeadRequirements(BaseModel):
    """Everything the agent believes about the buyer right now.

    Every field is optional: a fresh, vague inquiry legitimately fills almost
    none of them, and that emptiness is itself evidence the agent reasons over.
    """

    name: Optional[str] = None
    contact: Optional[str] = None
    budget_min: Optional[int] = Field(default=None, description="Rupees")
    budget_max: Optional[int] = Field(default=None, description="Rupees")
    locations: List[str] = Field(default_factory=list)
    property_type: Optional[str] = None
    bhk: Optional[int] = None
    min_sqft: Optional[int] = None
    timeline_months: Optional[float] = Field(
        default=None, description="Months until intended purchase"
    )
    timeline_text: Optional[str] = None
    financing_method: Optional[str] = None
    financing_readiness: FinancingReadiness = FinancingReadiness.UNKNOWN
    amenities: List[str] = Field(default_factory=list)
    parking_required: Optional[bool] = None
    furnishing: Optional[str] = None
    purpose: Purpose = Purpose.UNKNOWN
    viewing_ready: Optional[bool] = None
    notes: List[str] = Field(default_factory=list)
    original_inquiry: Optional[str] = None

    @field_validator("locations", "amenities", "notes", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v

    @field_validator("min_sqft", "bhk", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> Any:
        if v in (None, "", "null"):
            return None
        if isinstance(v, str):
            digits = "".join(ch for ch in v if ch.isdigit())
            return int(digits) if digits else None
        if isinstance(v, float):
            return int(v)
        return v

    @field_validator("budget_min", "budget_max", mode="before")
    @classmethod
    def _coerce_budget(cls, v: Any) -> Any:
        return parse_rupees(v)

    @field_validator("timeline_months", mode="before")
    @classmethod
    def _coerce_float(cls, v: Any) -> Any:
        if v in (None, "", "null"):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @field_validator("financing_readiness", mode="before")
    @classmethod
    def _coerce_readiness(cls, v: Any) -> Any:
        if v in (None, "", "null"):
            return FinancingReadiness.UNKNOWN
        if isinstance(v, str):
            key = v.strip().upper().replace(" ", "_").replace("-", "_")
            if key in FinancingReadiness.__members__:
                return key
            return FinancingReadiness.UNKNOWN
        return v

    @field_validator("purpose", mode="before")
    @classmethod
    def _coerce_purpose(cls, v: Any) -> Any:
        if v in (None, "", "null"):
            return Purpose.UNKNOWN
        if isinstance(v, str):
            key = v.strip().upper().replace(" ", "_").replace("-", "_")
            if key in Purpose.__members__:
                return key
            return Purpose.UNKNOWN
        return v

    def budget_label(self) -> str:
        if self.budget_min is None and self.budget_max is None:
            return "Not stated"
        if self.budget_min and self.budget_max and self.budget_min != self.budget_max:
            return f"{money(self.budget_min)} - {money(self.budget_max)}"
        return money(self.budget_max or self.budget_min)

    def timeline_label(self) -> str:
        if self.timeline_months is None:
            return self.timeline_text or "Not stated"
        months = self.timeline_months
        if months <= 1:
            return "Within a month"
        if months < 12:
            return f"~{months:.0f} months"
        return f"~{months / 12:.1f} years"


def parse_rupees(value: Any) -> Optional[int]:
    """Normalise any budget-ish value into whole rupees.

    Buyers (and models echoing them) write budgets as "65 lakh", "1.2 Cr",
    "6500000" or plain "65". Anything below 10,000 is read as lakhs, because no
    real property budget is a four-digit rupee amount.
    """
    if value in (None, "", "null"):
        return None
    multiplier = 1
    if isinstance(value, str):
        text = value.lower().replace(",", "").strip()
        if "cr" in text:
            multiplier = 10_000_000
        elif "lakh" in text or "lac" in text or "l" == text[-1:]:
            multiplier = 100_000
        number = "".join(ch for ch in text if ch.isdigit() or ch == ".")
        number = number.strip(".")
        if not number:
            return None
        try:
            value = float(number)
        except ValueError:
            return None
    try:
        amount = float(value) * multiplier
    except (TypeError, ValueError):
        return None
    if 0 < amount < 10_000:  # "65" almost certainly means 65 lakh
        amount *= 100_000
    return int(round(amount))


def money(value: Optional[int]) -> str:
    """Format rupees the way the Indian market talks about them."""
    if value is None:
        return "?"
    if value >= 10_000_000:
        text = f"Rs {value / 10_000_000:.2f} Cr"
        return text.replace(".00 Cr", " Cr")
    return f"Rs {value / 100_000:.0f} L"


# Fields that qualification cannot proceed without.
CRITICAL_FIELDS = ("budget", "locations", "timeline")


# --------------------------------------------------------------------------- #
# Deterministic outputs
# --------------------------------------------------------------------------- #
class PropertyMatch(BaseModel):
    property_id: str
    name: str
    location: str
    property_type: str
    bhk: Optional[int] = None
    price: int
    sqft: int
    availability: str
    match_pct: int
    reasons: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    """Deterministic, auditable facts handed to the reasoning stage."""

    completeness_pct: int = 0
    missing_critical_fields: List[str] = Field(default_factory=list)
    missing_secondary_fields: List[str] = Field(default_factory=list)
    heuristic_score: int = 0
    score_breakdown: Dict[str, int] = Field(default_factory=dict)
    budget_realism: Dict[str, Any] = Field(default_factory=dict)
    inventory_stats: Dict[str, Any] = Field(default_factory=dict)
    contradictions: List[str] = Field(default_factory=list)
    conversation_turns: int = 0
    top_match_pct: int = 0
    strong_match_count: int = 0


# --------------------------------------------------------------------------- #
# Stage 2 contract - the agent's decision
# --------------------------------------------------------------------------- #
class DraftMessage(BaseModel):
    audience: str = "BROKER"  # BROKER | BUYER
    channel: str = "Email (draft only - nothing is sent)"
    subject: str = ""
    body: str = ""


class AgentDecision(BaseModel):
    intent_score: int = Field(ge=0, le=100)
    intent_tier: IntentTier
    decision: NextAction
    reasoning: List[str] = Field(min_length=1)
    missing_information: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommended_next_step: str
    follow_up_question: Optional[str] = None
    summary_headline: str = ""
    draft_message: Optional[DraftMessage] = None
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    @field_validator("intent_score", mode="before")
    @classmethod
    def _clamp_score(cls, v: Any) -> Any:
        try:
            return max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            return 0

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_conf(cls, v: Any) -> Any:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.6

    @field_validator("reasoning", "missing_information", "risks", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v

    @field_validator("follow_up_question", "summary_headline", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("summary_headline", mode="before")
    @classmethod
    def _headline_default(cls, v: Any) -> Any:
        return v or ""

    @property
    def status(self) -> str:
        return ACTION_TO_STATUS.get(self.decision.value, LeadStatus.QUALIFYING.value)


class TurnResult(BaseModel):
    """Everything one agent turn produced - used by the UI and persisted."""

    lead_id: str
    requirements: LeadRequirements
    evidence: EvidencePack
    matches: List[PropertyMatch]
    decision: AgentDecision
    status: str
    previous_status: Optional[str] = None
    previous_tier: Optional[str] = None
    llm_provider: str = ""
    warnings: List[str] = Field(default_factory=list)
