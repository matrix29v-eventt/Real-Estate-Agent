import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class LLMResponseSchema(BaseModel):
    intent_score: int = Field(..., ge=0, le=100)
    intent_tier: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NEEDS_CLARIFICATION)$")
    decision: str = Field(
        ...,
        pattern="^(ASK_MORE_INFO|SHOW_MATCHING_PROPERTIES|ESCALATE_TO_BROKER|NURTURE_LEAD|LOW_PRIORITY_OR_DISCARD)$",
    )
    reasoning: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommended_next_step: str = Field(default="")
    follow_up_question: Optional[str] = None


class LLMProvider(ABC):
    @abstractmethod
    def generate_response(self, prompt: str, response_schema: type) -> Any:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key=None, model="gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", model)
        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                logger.warning("OpenAI package not installed")

    def is_available(self):
        return self.client is not None

    def generate_response(self, prompt: str, response_schema: type):
        if not self.is_available():
            raise RuntimeError("OpenAI client not available")
        system_prompt = (
            "You are a real estate lead qualification agent. Respond in strict JSON format matching the schema. "
            "Analyze the lead context and determine the next action. Be precise and evidence-based. "
            "Do not fabricate information. If information is insufficient, state what is missing."
        )
        from openai.types.chat import ChatCompletionMessageParam

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_object",
                "schema": response_schema.model_json_schema(),
            },
            temperature=0.3,
            max_tokens=1024,
        )
        content = response.choices[0].message.content
        return json.loads(content)


class OllamaProvider(LLMProvider):
    def __init__(self, base_url=None, model="llama3"):
        self.base_url = (
            os.getenv("OLLAMA_BASE_URL") or base_url or "http://localhost:11434"
        )
        self.model = os.getenv("OLLAMA_MODEL", model)
        self.available = False
        try:
            import httpx

            with httpx.Client(timeout=5) as client:
                r = client.get(f"{self.base_url}/api/tags")
                self.available = r.status_code == 200
        except Exception:
            self.available = False

    def is_available(self):
        return self.available

    def generate_response(self, prompt: str, response_schema: type):
        import httpx

        schema_def = response_schema.model_json_schema()
        payload = {
            "model": self.model,
            "prompt": f"{prompt}\n\nRespond in this exact JSON format:\n{json.dumps(schema_def, indent=2)}",
            "format": "json",
            "options": {"temperature": 0.3, "num_predict": 1024},
        }
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{self.base_url}/api/generate", json=payload)
            r.raise_for_status()
            result = r.json()
            text = result.get("response", "")
            return json.loads(text.strip())


def get_llm_provider():
    provider_name = os.getenv("LLM_PROVIDER", "openai")
    if provider_name == "ollama":
        provider = OllamaProvider()
        if provider.is_available():
            return provider
        logger.warning("Ollama not available, falling back")
    if provider_name == "openai":
        provider = OpenAIProvider()
        if provider.is_available():
            return provider
        logger.warning("OpenAI not available, falling back")
    return None


def llm_reasoning(
    lead_context: Dict[str, Any], matches: List[Dict], missing_fields: List[str]
) -> LLMResponseSchema:
    provider = get_llm_provider()
    prompt = build_prompt(lead_context, matches, missing_fields)
    try:
        if provider:
            raw = provider.generate_response(prompt, LLMResponseSchema)
            return LLMResponseSchema(**raw)
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
    return rule_based_reasoning(lead_context, matches, missing_fields)


def build_prompt(lead_context, matches, missing_fields):
    budget = (
        lead_context.get("budget_min")
        and lead_context.get("budget_max")
        and f"{lead_context['budget_min'] / 100000:.1f}-{lead_context['budget_max'] / 100000:.1f}L"
        or "Not specified"
    )
    locations = ", ".join(lead_context.get("locations", [])) or "Not specified"
    bhk = lead_context.get("bhk") or "Not specified"
    timeline = lead_context.get("timeline_months") or "Not specified"
    financing = lead_context.get("financing") or "Not specified"
    financing_ready = lead_context.get("financing_ready", False)
    inquiry = lead_context.get("original_inquiry", "")

    match_summaries = []
    for m in matches[:5]:
        p = m["property"]
        match_summaries.append(
            f"  - {p['name']} in {p['location']}: {p['bhk']}BHK, {p['price'] / 100000:.1f}L, {m['match_score']}% match"
        )

    matches_text = "\n".join(match_summaries) if match_summaries else "No matches found"

    prompt = f"""Analyze this real estate lead and determine the next action.

LEAD INQUIRY: {inquiry}

EXTRACTED REQUIREMENTS:
- Budget: {budget}
- Locations: {locations}
- BHK: {bhk}
- Timeline: {timeline} months
- Financing: {financing} (Ready: {financing_ready})
- Missing fields: {", ".join(missing_fields) if missing_fields else "None"}

PROPERTY MATCHES:
{matches_text}

Determine:
1. intent_score (0-100) based on evidence
2. intent_tier (HIGH, MEDIUM, LOW, NEEDS_CLARIFICATION)
3. decision (ASK_MORE_INFO, SHOW_MATCHING_PROPERTIES, ESCALATE_TO_BROKER, NURTURE_LEAD, LOW_PRIORITY_OR_DISCARD)
4. reasoning bullets (why this decision)
5. missing_information (what's still needed)
6. risks (potential issues)
7. recommended_next_step
8. follow_up_question (null if no more questions needed)

Respond in JSON matching the schema exactly."""
    return prompt


def rule_based_reasoning(lead_context, matches, missing_fields):
    budget_min = lead_context.get("budget_min")
    budget_max = lead_context.get("budget_max")
    locations = lead_context.get("locations", [])
    timeline = lead_context.get("timeline_months")
    financing_ready = lead_context.get("financing_ready", False)
    bhk = lead_context.get("bhk")
    inquiry = lead_context.get("original_inquiry", "")

    missing_budget = not budget_min or not budget_max
    missing_location = len(locations) == 0
    missing_timeline = timeline is None or timeline > 24
    has_requirement = bhk is not None or len(locations) > 0

    score = 0
    if not missing_budget:
        score += 25
    if not missing_location:
        score += 25
    if timeline and timeline <= 6:
        score += 20
    elif timeline and timeline <= 12:
        score += 10
    if financing_ready:
        score += 15
    if has_requirement:
        score += 15

    if len(matches) > 0:
        avg_match = sum(m["match_score"] for m in matches[:3]) / min(3, len(matches))
        if avg_match >= 70:
            score += 15
        elif avg_match >= 40:
            score += 8

    score = min(100, score)

    if score >= 80 and len(missing_fields) == 0:
        tier = "HIGH"
        decision = "ESCALATE_TO_BROKER"
    elif score >= 60:
        tier = "MEDIUM"
        decision = "SHOW_MATCHING_PROPERTIES" if matches else "ASK_MORE_INFO"
    elif score >= 30:
        tier = "NEEDS_CLARIFICATION" if missing_fields else "MEDIUM"
        decision = "ASK_MORE_INFO"
    else:
        tier = "LOW"
        decision = "LOW_PRIORITY_OR_DISCARD"

    if missing_timeline and timeline and timeline > 24:
        tier = "LOW"
        decision = "NURTURE_LEAD"

    reasoning = []
    if not missing_budget:
        reasoning.append(
            f"Budget clearly defined at {budget_min / 100000:.1f}-{budget_max / 100000:.1f}L"
        )
    if not missing_location:
        reasoning.append(f"Location specified: {', '.join(locations)}")
    if timeline:
        reasoning.append(f"Purchase timeline: {timeline} months")
    if financing_ready:
        reasoning.append("Financing is already in progress")
    if len(matches) > 0:
        reasoning.append(
            f"{len(matches)} property match(es) found with avg score {int(sum(m['match_score'] for m in matches[:3]) / min(3, len(matches)))}%"
        )

    if missing_fields:
        reasoning.append(f"Missing information: {', '.join(missing_fields)}")
        follow_up = f"I can help narrow this down. {', '.join(missing_fields[:2])}. Could you provide these details?"
    else:
        follow_up = None

    return LLMResponseSchema(
        intent_score=score,
        intent_tier=tier,
        decision=decision,
        reasoning=reasoning,
        missing_information=missing_fields,
        risks=[],
        recommended_next_step=f"{'Escalate to broker for immediate follow-up' if decision == 'ESCALATE_TO_BROKER' else 'Continue qualification' if decision == 'ASK_MORE_INFO' else 'Show matching properties' if decision == 'SHOW_MATCHING_PROPERTIES' else 'Nurture lead over time' if decision == 'NURTURE_LEAD' else 'Deprioritize or discard lead'}",
        follow_up_question=follow_up,
    )
