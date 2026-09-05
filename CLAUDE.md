# CLAUDE.md — repository instructions

Stable development rules for this repository. Changing project *state* belongs in
`PROJECT_CONTEXT.md`, not here.

## What this project is

An AI real estate **lead qualification and routing** agent (CYMONIC hackathon,
Problem #4). It decides which inquiries deserve broker time. It is not a
property-search chatbot.

## Commands

```bash
pip install -r requirements.txt
streamlit run app.py                 # the app
python -m pytest -q                  # tests (no network, scripted LLM)
python scripts/run_scenarios.py      # manual end-to-end demo, needs a real model
```

## Non-negotiable design rules

1. **The next-action decision is always LLM reasoning.** Never add a rule that
   selects `decision` from a number (`if score > 80: escalate`). Deterministic
   Python is for filtering, matching, arithmetic, validation and persistence.
   The heuristic rubric in `services/signals.py` is *evidence handed to the
   agent*, and the prompt says so explicitly. Keep it that way.
2. **Never fabricate model output.** If no provider is configured, raise
   `LLMUnavailable` and let the UI explain how to configure one. On invalid
   structured output, retry once with the validation error, then fail loudly.
3. **Nothing is sent externally.** No email, SMS, WhatsApp or webhook. Actions
   that imply a message produce a draft rendered in the UI (`services/drafts.py`).
4. **Never claim identity or KYC verification.** The vocabulary is "buyer
   intent", "lead quality", "qualification".
5. **Never invent properties.** Matches come from the database only. If nothing
   fits, say nothing fits.
6. **Never commit secrets.** `.env` is git-ignored; `.env.example` holds names
   with empty values.
7. **Context merges, never resets.** A follow-up answer must preserve everything
   already known (`agent._merge_preserving` is the safety net behind the model).

## Where things live

- LLM calls: only in `services/llm_service.py` (providers) and
  `services/agent.py` (the two stages). No other module imports a vendor SDK.
- Deterministic logic: `services/matcher.py`, `services/signals.py`.
- Contracts: `models/schemas.py`. Validate every model output through Pydantic
  before persisting it.
- Persistence: `services/db.py` only. Every agent turn must write an
  `agent_actions` row with both snapshots.
- UI: `app.py` + `ui/`. Presentation only, no business logic.

## Conventions

- Python 3.11, standard library first, minimal dependencies.
- Type hints on public functions; `from __future__ import annotations` at the top.
- Money is whole rupees internally; format for display with `models.schemas.money`.
- Tests must not hit the network — use `ScriptedProvider` from `tests/conftest.py`.
- Prefer plain ASCII in source strings (the UI runs in a Windows terminal too).
- Keep the UI clean and functional; do not add heavy custom CSS.

## Before finishing any session

Run `python -m pytest -q`, then update `PROJECT_CONTEXT.md` (status, last work
performed, next steps) and commit it.
