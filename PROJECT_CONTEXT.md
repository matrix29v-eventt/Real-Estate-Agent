# PROJECT_CONTEXT.md — Handoff / Continuity File

> Purpose: allow **any** other AI coding agent or engineer to resume this project
> from the repository alone, with no additional explanation from the user.
> Update this file after every meaningful milestone.

**Last updated:** initial scaffold (phase 0)

---

## Project Objective

Build an **AI Real Estate Lead Qualification & Routing Agent** for the CYMONIC
Campus Recruitment — Agentic Workforce Hackathon (Problem #4).

The system answers one business question:

> "Which property inquiries deserve a broker's immediate attention, which need
> more qualification, and which should be deprioritized?"

It is **not** a generic property-search chatbot. Every conversation must feed
qualification → matching → routing → a business action.

---

## Hackathon Requirements (must not be forgotten)

- Streamlit UI, clean and functional; **no heavy custom CSS**.
- **No external communication** (no email/WhatsApp/Twilio). Notifications,
  broker escalations and buyer replies are rendered as **drafts inside the app**.
- No dataset provided → we generate our own realistic synthetic dataset
  (Thiruvananthapuram / Kerala market).
- **The final next-action decision must be dynamic LLM reasoning**, never
  `if score > 80: escalate`. Deterministic Python is allowed (and expected) for
  filtering, matching, scoring evidence, validation, persistence.
- Never claim identity/KYC verification — the term is **Buyer Intent /
  Lead Quality / Qualification**.
- Never fabricate LLM output when no model is configured: show a clear warning.
- Secrets never committed. `.env.example` only.

---

## Technology Stack

- Python 3.11
- Streamlit (UI)
- SQLite (persistence, stdlib `sqlite3`)
- Pandas (dashboard tables)
- Pydantic v2 (structured agent I/O contracts)
- `anthropic` SDK (primary LLM provider) + optional local Ollama via `requests`
- pytest (tests)

---

## Repository Structure

(Filled in as modules land — see "Implemented Features".)

```
.
├── app.py                  # Streamlit entry point (3 tabs)
├── config.py               # paths, env loading, constants
├── models/schemas.py       # Pydantic contracts (requirements, decision, matches)
├── services/
│   ├── db.py               # SQLite schema + CRUD + audit trail
│   ├── llm_service.py      # provider abstraction (Anthropic / Ollama)
│   ├── matcher.py          # deterministic property matching engine
│   ├── signals.py          # deterministic evidence pack + heuristic score
│   ├── agent.py            # orchestrating agent pipeline
│   └── drafts.py           # in-app notification / email draft rendering
├── data/
│   ├── property_seed.py    # ~50 synthetic properties
│   └── lead_seed.py        # ~20 historical leads
├── ui/                     # Streamlit view modules
├── tests/                  # pytest suite
├── PROJECT_CONTEXT.md      # THIS FILE
├── CLAUDE.md               # stable repo instructions
└── README.md
```

---

## Implemented Features

- [x] Repository initialised, `.gitignore`, `.env.example`, `requirements.txt`
- [ ] Config + Pydantic contracts
- [ ] SQLite schema + seeding
- [ ] Property dataset
- [ ] Lead dataset
- [ ] Deterministic property matcher
- [ ] Deterministic evidence/signal computation
- [ ] LLM provider abstraction
- [ ] Agent pipeline (extract → evidence → reason → act → persist)
- [ ] Conversational follow-up with context merging
- [ ] Streamlit UI (3 tabs)
- [ ] Tests
- [ ] README

---

## Current Status

Phase 0: scaffolding only. No runnable application yet.

## Pending Work

Everything below "Implemented Features" that is unchecked, in listed order.

## Known Bugs / Issues

None yet.

## Environment Variables (names only — never values)

`LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OLLAMA_BASE_URL`,
`OLLAMA_MODEL`, `REALESTATE_DB`, `LLM_TIMEOUT_SECONDS`.

## Running the Project

```bash
pip install -r requirements.txt
cp .env.example .env      # then edit .env
streamlit run app.py
```

## Testing

```bash
python -m pytest -q
```

Status: no tests yet.

## Git Status

- Branch: `main`
- Remote: https://github.com/matrix29v-eventt/Real-Estate-Agent.git (was empty)
- Nothing committed yet at time of writing.

## Last Work Performed

Created directory skeleton, `.gitignore`, `.env.example`, `requirements.txt`,
and this handoff file.

## NEXT STEPS

1. Write `config.py` and `models/schemas.py`.
2. Write `data/property_seed.py` (~50 properties) and `data/lead_seed.py`.
3. Write `services/db.py`, initialise and seed the database.
4. Commit `chore: initialize real estate agent project`.
