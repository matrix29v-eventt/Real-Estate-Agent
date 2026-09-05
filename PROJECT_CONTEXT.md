# PROJECT_CONTEXT.md — Handoff / Continuity File

> Purpose: allow **any** other AI coding agent or engineer to resume this project
> from the repository alone, with no additional explanation from the user.
> Update after every meaningful milestone.

**Last updated:** phase 6 — application complete, pushed, 63 tests green, two live-use bugs found and fixed.

---

## Project Objective

An **AI Real Estate Lead Qualification & Routing Agent** for the CYMONIC Campus
Recruitment — Agentic Workforce Hackathon (Problem #4).

It answers one business question:

> "Which property inquiries deserve a broker's immediate attention, which need
> more qualification, and which should be deprioritised?"

It is **not** a generic property-search chatbot. Every conversation feeds
qualification → matching → routing → a business action.

---

## Hackathon Requirements (must not be forgotten)

- Streamlit UI, clean and functional; **no heavy custom CSS**.
- **No external communication** (no email/WhatsApp/Twilio/webhooks). Broker
  escalations and buyer replies are rendered as **drafts inside the app**.
- No dataset provided → own synthetic dataset (Thiruvananthapuram market).
- **The final next-action decision must be dynamic LLM reasoning**, never
  `if score > 80: escalate`. Deterministic Python is allowed and expected for
  filtering, matching, scoring evidence, validation and persistence.
- Never claim identity/KYC verification — the vocabulary is **buyer intent /
  lead quality / qualification**.
- Never fabricate LLM output when no model is configured; show a clear warning.
- Secrets never committed. `.env.example` only.

---

## Technology Stack

Python 3.11 · Streamlit 1.63 · SQLite (stdlib `sqlite3`) · Pandas · Pydantic v2 ·
`anthropic` SDK 1.4 · optional Ollama via `requests` · pytest 8.

---

## Repository Structure

```
.
├── app.py                     # Streamlit entry point: 3 tabs + sidebar LLM status
├── config.py                  # paths, env loading, market constants, area adjacency
├── CLAUDE.md                  # stable repo rules for future agents
├── PROJECT_CONTEXT.md         # THIS FILE — changing project state
├── README.md                  # full project documentation
├── requirements.txt
├── .env.example               # variable NAMES only, no values
├── .gitignore                 # ignores .env, *.db, __pycache__, venvs
├── models/
│   └── schemas.py             # Pydantic contracts, enums, rupee parsing
├── services/
│   ├── db.py                  # SQLite schema, CRUD, audit trail, metrics
│   ├── matcher.py             # deterministic matching, inventory stats, realism
│   ├── signals.py             # missing fields, contradictions, heuristic rubric
│   ├── llm_service.py         # provider abstraction (Anthropic / Ollama)
│   ├── agent.py               # the two-stage pipeline + persistence
│   └── drafts.py              # in-app draft rendering (never sends)
├── ui/
│   ├── components.py          # shared render helpers
│   ├── new_lead.py            # tab A
│   ├── analysis.py            # tab B (+ rebuild_from_db)
│   └── dashboard.py           # tab C
├── data/
│   ├── property_seed.py       # 53 synthetic properties
│   ├── lead_seed.py           # 20 historical leads
│   └── realestate.db          # generated, git-ignored
├── scripts/
│   └── run_scenarios.py       # manual end-to-end demo harness (needs a real model)
└── tests/                     # 63 pytest tests, no network
    ├── conftest.py            # temp_db fixture + ScriptedProvider
    ├── test_db.py  test_matcher.py  test_signals.py
    ├── test_schemas.py  test_agent.py
    └── test_ui_smoke.py       # streamlit.testing.v1.AppTest render tests
```

---

## Database Schema

| Table | Key fields |
|---|---|
| `properties` | `property_id` PK, name, location, property_type, bhk, price, sqft, parking, furnishing, amenities (CSV), availability, builder, possession_status, possession_date, tags (CSV), created_at |
| `leads` | `lead_id` PK, name, contact, original_inquiry, `requirements_json`, intent_score, intent_tier, status, current_action, recommended_next_step, `summary_json`, created_at, updated_at |
| `conversations` | `turn_id` PK, lead_id, turn_index, role (`buyer`/`agent`), message, created_at |
| `agent_actions` | `action_id` PK, lead_id, timestamp, decision, intent_score, intent_tier, `reasoning_json`, `input_snapshot`, `output_snapshot`, status_before, status_after, llm_provider |

Statuses: `NEW, QUALIFYING, NEEDS_INFORMATION, QUALIFIED, BROKER_ESCALATION,
NURTURING, LOW_PRIORITY`. `models.schemas.ACTION_TO_STATUS` maps each action to a
status — clerical bookkeeping applied *after* the agent decides.

---

## Agent Workflow

```
buyer message + stored lead context
 1. [LLM]  extract_requirements()   understanding + context merge
           safety net: agent._merge_preserving() restores any field the model
           dropped, accumulates notes, keeps original_inquiry
 2. [code] matcher.match_properties()   weighted compatibility, top 5, min 35%
 3. [code] signals.compute_evidence()   completeness, missing critical/secondary
           fields, budget realism vs market floor, contradictions vs previous
           snapshot, heuristic rubric score + penalties
 4. [LLM]  reason_next_action()    situation brief + full JSON evidence + matches
           + transcript → AgentDecision
 5. [code] validate → db.update_lead → db.add_turn → db.record_action
           → build_summary → TurnResult
```

Two LLM calls per turn (`effort="low"` for extraction, `"medium"` for reasoning).

### Decision enum

`ASK_MORE_INFO`, `SHOW_MATCHING_PROPERTIES`, `ESCALATE_TO_BROKER`,
`NURTURE_LEAD`, `RESET_EXPECTATIONS`, `LOW_PRIORITY_OR_DISCARD`.

---

## Agent Input/Output Contracts

**Stage 1 — `EXTRACTION_SCHEMA`** (in `services/agent.py`) → `LeadRequirements`:
name, contact, budget_min, budget_max, locations[], property_type, bhk,
min_sqft, timeline_months, timeline_text, financing_method, financing_readiness,
amenities[], parking_required, furnishing, purpose, viewing_ready, notes[].

**Stage 2 — `DECISION_SCHEMA`** → `AgentDecision`:

```json
{
  "intent_score": 88,
  "intent_tier": "HIGH",
  "decision": "ESCALATE_TO_BROKER",
  "reasoning": ["...", "..."],
  "missing_information": [],
  "risks": [],
  "recommended_next_step": "Broker should arrange a property viewing.",
  "follow_up_question": null,
  "summary_headline": "Loan-ready 3BHK buyer for the Technopark corridor",
  "confidence": 0.85,
  "draft_message": {"audience": "BROKER", "channel": "...", "subject": "...", "body": "..."}
}
```

Invalid output → one retry with the validation error fed back → then
`LLMCallError`. Nothing is fabricated.

---

## Business Decisions (and why)

- **Two LLM calls, not five.** Parsing and judgement are genuinely different
  tasks; everything else is arithmetic. Keeps latency and cost sane.
- **Heuristic rubric is evidence, not a rule.** `signals.compute_evidence`
  produces a transparent 0–100 score with a visible breakdown; the prompt calls
  it "not a rule and not a threshold". The UI warns when the agent's own score
  diverges by ≥25, because the disagreement is the interesting part.
- **`_merge_preserving` safety net.** The model is asked for the complete merged
  state, but a dropped field would silently lose context, so known values are
  restored in Python. Explicit new values still override.
- **Out-of-budget listings capped at 45% match.** A property 10× over budget is
  never a "strong match", however well it scores elsewhere. It stays visible so
  the agent can see the closest real inventory.
- **`matching_is_meaningful` flag.** Scoring the catalogue against "a nice flat
  in Trivandrum" yields high percentages that mean nothing; the evidence pack
  says so and the UI shows a warning.
- **Uneven dataset on purpose.** No 4BHK under Rs 1.42 Cr, Kowdiar floor
  Rs 95 L, sold-out/on-hold records, under-construction possession dates.
- **`num_ctx: 16384` for Ollama.** Its small default context silently truncated
  answers mid-JSON.
- **Situation brief before the JSON.** A short plain-English digest of the
  decision-relevant facts materially improves adherence and is auditable.
- **Keyed `active_view` selector instead of `st.tabs`.** `st.tabs` resets to the
  first tab on every rerun, so "Open in Lead Analysis" never landed. Switch views
  by setting `st.session_state["pending_view"]` then `st.rerun()`; `app.py`
  applies it before the widget renders (a widget key cannot be written after the
  widget exists in the same run).
- **`run_turn` rolls back a lead it created if the turn fails.** Observed twice
  in live use against a slow local model: a timeout left a half-formed `NEW` lead
  with a conversation turn and no decision sitting in the dashboard. Existing
  leads are never rolled back.

---

## Implemented Features

- [x] Repository, `.gitignore`, `.env.example`, `requirements.txt`
- [x] Config + Pydantic contracts (`models/schemas.py`)
- [x] SQLite schema + seeding + audit trail (`services/db.py`)
- [x] Property dataset — 53 records with deliberate gaps
- [x] Lead dataset — 20 historical leads with conversations and decisions
- [x] Deterministic property matcher with reasons, gaps, realism verdicts
- [x] Deterministic evidence pack + contradiction detection
- [x] LLM provider abstraction (Anthropic + Ollama), structured JSON, recovery
- [x] Agent pipeline: extract → match → evidence → reason → act → persist
- [x] Conversational follow-up with context merging
- [x] Structured lead summary persisted per lead
- [x] Decision audit trail with input/output snapshots
- [x] Streamlit UI — 3 tabs (New Lead, Lead Analysis, Dashboard)
- [x] In-app draft rendering; nothing is sent externally
- [x] 63 pytest tests, all passing, no network (incl. AppTest render smoke tests)
- [x] `scripts/run_scenarios.py` demo harness
- [x] README.md + CLAUDE.md + this file
- [x] All three views verified rendering (AppTest + browser)
- [ ] Final verification pass with `claude-opus-5` (see Pending Work)
- [x] Pushed to GitHub (branch `claude/lead-qualification-agent`, commit `d6ee343`)

---

## Current Status

**The application is complete, runs, and is pushed.**

- `streamlit run app.py` starts, seeds the DB and renders all three views
  (verified both in a browser and headlessly via `AppTest`).
- `python -m pytest -q` → **63 passed**.
- `scripts/run_scenarios.py` ran all five demo scenarios end to end against a
  local Ollama model with **0 pipeline failures** — extraction, context merging,
  matching, evidence, decision, persistence and status transitions all worked.

**Two real bugs were found by using the app and are fixed:**

1. `st.tabs` reset to the first tab on every rerun, so the dashboard's
   "Open in Lead Analysis" button never landed. Replaced with a keyed view
   selector.
2. A turn that failed before reaching a decision left an orphan `NEW` lead in the
   dashboard. `run_turn` now rolls back a lead it created.

**Caveat on decision quality:** the only models available locally during
development were small (`llama3.2:3b`, `gemma4`). `llama3.2:3b` follows the
reasoning instructions poorly and tends to pick `ASK_MORE_INFO` for everything;
`gemma4` produces sensible decisions (scenario 1 → HIGH 95/100, scenario 2 →
`ASK_MORE_INFO` / NEEDS_CLARIFICATION 20/100) but takes minutes per call on CPU.
This is a model-capability ceiling, not a code defect. The prompts are written
for `claude-opus-5`; set `ANTHROPIC_API_KEY` for the intended behaviour.

**Fresh-clone verified:** `git clone -b claude/lead-qualification-agent ...` into
a clean directory contains no `.env` and passes all 63 tests.

**Note on the local `.env`:** a `.env` exists in the working tree (created by the
user) pointing at `ollama/gemma4`. It is git-ignored and untracked. Because
gemma4 is slow on CPU, raise `LLM_TIMEOUT_SECONDS` well above the 90s default or
switch to Anthropic — the default timeout is what produced the orphan leads.

---

## Pending Work (priority order)

1. Run `python scripts/run_scenarios.py` with `ANTHROPIC_API_KEY` set and confirm
   the five scenarios produce the expected actions. Record results here.
   (A full pass on `gemma4` was attempted but abandoned: it takes many minutes
   per call on CPU and competed with the user's own running app for the same
   Ollama server. The full five-scenario pass on `llama3.2:3b` completed with
   0 pipeline failures, which is what proves the plumbing.)
2. Decide with the user how `claude/lead-qualification-agent` relates to the
   parallel implementation already on `main` (see Git Status). Do not force-push.
3. Optional polish: a small "before → after" delta banner on the Lead Analysis
   tab making the scenario-5 decision change even more obvious.

---

## Known Bugs / Issues

- None open.
- Fixed earlier: `summary_headline` had two conflicting `mode="before"`
  validators; the second returned `None` for a non-optional `str`, which made
  `ui.analysis.rebuild_from_db` return `None` for every seeded lead.
- Fixed earlier: Ollama truncated decision JSON mid-answer until `num_ctx` was
  raised to 16384.
- Fixed earlier: `P012` had a possession date in the past.
- Note: `git` warns `LF will be replaced by CRLF` on Windows. Cosmetic.

---

## Environment Variables (names only — never values)

`LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OLLAMA_BASE_URL`,
`OLLAMA_MODEL`, `REALESTATE_DB`, `LLM_TIMEOUT_SECONDS`.

---

## Running the Project

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env and set ANTHROPIC_API_KEY
streamlit run app.py
```

The database is created and seeded on first launch at `data/realestate.db`.
"Reset demo data" in the sidebar rebuilds it.

## Testing

```bash
python -m pytest -q                 # 51 passed
python scripts/run_scenarios.py     # manual, needs a real model
```

Tests never touch the network: `tests/conftest.py` provides `ScriptedProvider`,
which returns pre-scripted JSON payloads in order.

---

## Git Status

- Branch: **`claude/lead-qualification-agent`** (renamed from `main` — see below)
- Remote: `origin` → https://github.com/matrix29v-eventt/Real-Estate-Agent.git
- **Pushed successfully** to `origin/claude/lead-qualification-agent`.
- Latest pushed commit at time of writing: **`843457c`**
  ("test: add Streamlit render smoke tests and a timeout hint").
- Working tree clean at time of push.

### IMPORTANT — a parallel implementation exists on `main`

The repository was empty when this work started. Partway through, the repo owner
(`matrix29v-eventt`) pushed a **separate, complete implementation of the same
problem** to `main`:

```
7ae9174 2026-09-05 10:54 fix: parse JSON fields in database query results
16d3b8d 2026-09-05 10:39 docs: update PROJECT_CONTEXT.md with final completion status
5678dcf 2026-09-05 10:39 feat: complete real estate lead qualification agent
```

Their layout differs (`services/database.py`, `services/property_matcher.py`,
`data/properties.py`, `data/leads.py`, `tests/test_core.py`).

The two histories are **unrelated** (this branch started from a fresh `git init`),
so they cannot be fast-forwarded into each other. This work was therefore pushed
to its own branch and `main` was left untouched. **Do not force-push over `main`.**

The user must decide which implementation is the submission:

- keep both and open a PR from `claude/lead-qualification-agent`, or
- adopt this branch as `main`, or
- cherry-pick specific pieces across.

Commits on this branch:

1. `b3c9bba` chore: initialize real estate agent project scaffolding
2. `b6f11da` feat: add synthetic property and lead datasets with SQLite persistence
3. `6cb5288` feat: implement matching, evidence signals, LLM abstraction and agent pipeline
4. `61e7ad4` feat: build Streamlit lead qualification UI with three views
5. `d6ee343` docs: add README, CLAUDE.md, handoff context and scenario harness
6. `32cac89` docs: record push status and the parallel implementation on main
7. `d050a4e` fix: keep view selection across reruns and roll back orphan leads
8. `843457c` test: add Streamlit render smoke tests and a timeout hint

---

## Last Work Performed

Replaced `st.tabs` with a keyed view selector so navigation survives reruns;
made `run_turn` roll back a lead it created when a turn fails; added
`tests/test_ui_smoke.py` (10 `AppTest` render tests covering all three views,
every lead archetype, dashboard metrics and the missing-LLM path); added an
actionable timeout hint to the inquiry form; refreshed README and CLAUDE.md.

---

## NEXT STEPS

1. `cd "F:/Real Estate - Cymonic"`
2. `python -m pytest -q` — expect 51 passed.
3. With `ANTHROPIC_API_KEY` set, run `python scripts/run_scenarios.py` and record
   the five decisions in "Current Status".
4. Ask the user how to reconcile this branch with `main` before any merge or
   force-push. Both implementations are complete; nothing should be deleted
   without the user's explicit decision.
5. Update this file and commit again.
