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
7. **The sign-in is a demo role switch, never call it authentication.**
   `services/auth.py` has no accounts, stores no passwords, and gates broker
   access on one shared plain-text code. Do not add password hashing, "secure
   login" wording, or anything that implies it protects real data. If real auth
   is ever needed, replace the module with an identity provider.
8. **Buyers never see broker internals.** Intent scores, the heuristic rubric,
   the decision enum and the broker draft are broker-facing. `ui/buyer.py`
   translates the decision into buyer-appropriate wording via `BUYER_STATUS`.
   Always scope buyer queries with `db.list_leads(owner=...)` and verify
   `lead["owner"]` before rendering a lead in the buyer portal.
9. **Context merges, never resets.** A follow-up answer must preserve everything
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
- Views are render-tested with `streamlit.testing.v1.AppTest`
  (`tests/test_ui_smoke.py`); add a case there when you add a view. Inject a
  role with `app.session_state[auth.SESSION_KEY] = <Account>`; without one the
  app renders the login page.
- Schema changes must be added to `db._migrate()` as well as `SCHEMA`, so an
  existing demo database survives. Indexes on new columns belong in `_migrate`,
  not `SCHEMA` — `SCHEMA` runs before the column exists.
- Navigation uses a keyed `active_view` selector, not `st.tabs`, because
  `st.tabs` resets to the first tab on every rerun. Switch views by setting
  `st.session_state["pending_view"]` and calling `st.rerun()`.
- Prefer plain ASCII in source strings (the UI runs in a Windows terminal too).
- Keep the UI clean and functional; do not add heavy custom CSS.

## Before finishing any session

Run `python -m pytest -q`, then update `PROJECT_CONTEXT.md` (status, last work
performed, next steps) and commit it.
