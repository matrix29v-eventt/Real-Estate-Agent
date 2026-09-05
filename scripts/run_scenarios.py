"""Run the five demo scenarios end to end against the configured LLM.

This is a manual verification harness, not a unit test: it needs a real model
and it costs a real API call per turn. The pytest suite covers the pipeline with
a scripted provider and never touches a network.

    python scripts/run_scenarios.py
    python scripts/run_scenarios.py --only 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.schemas import TurnResult  # noqa: E402
from services import agent, db, llm_service  # noqa: E402

# (title, [(buyer message, what we expect the agent to grapple with)])
SCENARIOS: List[Tuple[str, List[Tuple[str, str]]]] = [
    (
        "1. High-intent buyer",
        [(
            "Looking for a 3BHK apartment around Technopark or Kazhakkoottam. Budget "
            "65-75 lakh. Planning to purchase within 2 months. Need parking and "
            "preferably a gated community. Home loan is already being processed.",
            "complete requirements, urgent timeline, several strong matches",
        )],
    ),
    (
        "2. Ambiguous inquiry",
        [(
            "I need a nice flat in Trivandrum.",
            "critical information missing, should clarify rather than qualify",
        )],
    ),
    (
        "3. Unrealistic requirement",
        [(
            "I want a 4BHK premium property in Kowdiar for 25 lakh.",
            "budget roughly 10x below the real price floor, no viable matches",
        )],
    ),
    (
        "4. Long-term browser",
        [(
            "Looking at 3BHK properties around 80 lakh but probably won't buy for "
            "another 18 months.",
            "realistic budget but no urgency; timeline must appear in the reasoning",
        )],
    ),
    (
        "5. Context change across turns",
        [
            ("I am looking for a flat in Trivandrum, nothing decided yet.",
             "first turn should be a clarification, not a qualification"),
            ("Around 65-70 lakh, close to Technopark, within two months. "
             "My home loan is already approved and I can view this weekend.",
             "the decision should visibly change now that context exists"),
        ],
    ),
]


def _print_turn(index: int, message: str, expectation: str, result: TurnResult) -> None:
    print(f"\n  Turn {index}: {message}")
    print(f"  (looking for: {expectation})")
    print(f"  Requirements : budget={result.requirements.budget_label()} "
          f"| areas={', '.join(result.requirements.locations) or '-'} "
          f"| {result.requirements.bhk or '-'} BHK "
          f"| timeline={result.requirements.timeline_label()} "
          f"| financing={result.requirements.financing_readiness.value}")
    print(f"  Evidence     : heuristic={result.evidence.heuristic_score} "
          f"completeness={result.evidence.completeness_pct}% "
          f"missing={result.evidence.missing_critical_fields or 'none'} "
          f"realism={result.evidence.budget_realism.get('verdict')} "
          f"strong_matches={result.evidence.strong_match_count}")
    print(f"  Matches      : "
          + (", ".join(f"{m.property_id} {m.match_pct}%" for m in result.matches) or "none"))
    print(f"  DECISION     : {result.decision.decision.value} "
          f"({result.decision.intent_tier.value}, {result.decision.intent_score}/100)")
    for line in result.decision.reasoning:
        print(f"    - {line}")
    print(f"  Next step    : {result.decision.recommended_next_step}")
    if result.decision.follow_up_question:
        print(f"  Follow-up    : {result.decision.follow_up_question}")
    print(f"  Status       : {result.previous_status} -> {result.status}")
    for warning in result.warnings:
        print(f"  ! {warning}")


def main(only: Optional[int] = None, reset: bool = True) -> int:
    try:
        provider = llm_service.get_provider()
    except llm_service.LLMUnavailable as exc:
        print(f"No LLM configured, so nothing was run.\n{exc}")
        return 2

    if reset:
        db.reset_db()
    db.ensure_seeded()
    print(f"Provider: {provider.label()}")

    failures = 0
    for number, (title, turns) in enumerate(SCENARIOS, start=1):
        if only and number != only:
            continue
        print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
        lead_id = None
        for index, (message, expectation) in enumerate(turns, start=1):
            try:
                result = agent.run_turn(message, lead_id=lead_id, provider=provider)
            except Exception as exc:  # noqa: BLE001 - harness reports, does not hide
                print(f"  FAILED: {exc}")
                failures += 1
                break
            lead_id = result.lead_id
            _print_turn(index, message, expectation, result)

    print(f"\n{'=' * 78}")
    print(f"Scenarios finished with {failures} failure(s).")
    print("Open the Streamlit app to inspect the resulting leads and audit trail.")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", type=int, help="run a single scenario number")
    parser.add_argument("--keep", action="store_true",
                        help="keep the existing database instead of resetting it")
    args = parser.parse_args()
    raise SystemExit(main(only=args.only, reset=not args.keep))
