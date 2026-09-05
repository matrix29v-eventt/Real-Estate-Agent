# CLAUDE.md

## Repository Overview

Real Estate Lead Qualification & Routing Agent — Streamlit application using Python, SQLite, and LLM-based agentic reasoning.

## Key Files

- `app.py` — Streamlit UI (3 tabs: New Lead, Lead Analysis, Lead Dashboard)
- `services/agent.py` — Agent orchestration pipeline (parse, assess, match, qualify, decide)
- `services/database.py` — SQLite layer with all CRUD operations
- `services/property_matcher.py` — Deterministic weighted property matching
- `services/llm_service.py` — LLM provider abstraction (OpenAI + Ollama fallback)
- `data/properties.py` — 50 synthetic properties (Kerala market)
- `data/leads.py` — 20 seed historical leads
- `tests/test_core.py` — 30 pytest tests

## Important Notes

- **Never commit `.env` or secrets.** Use `.env.example` as template.
- `services/database.py` uses `DB_PATH` env variable for database location (defaults to `data/app.db`).
- The `lead_id` in `services/agent.py` is auto-generated sequentially (`L001`, `L002`, etc.).
- `parse_inquiry()` in `services/agent.py` extracts structured data from natural language.
- `analyze_lead()` in `services/agent.py` runs the full qualification pipeline.
- `follow_up_inquiry()` merges new answers into existing lead context.
- The LLM fallback (`rule_based_reasoning`) is used when no LLM provider is configured.
- Streamlit app uses `st.session_state` for current lead state across page reruns.
- The `property_matcher.py` filters properties with `final_score >= 50` threshold.

## Running the Project

```bash
streamlit run app.py
```

## Running Tests

```bash
pytest tests/test_core.py -v
```

Tests use a separate database (`data/test_app.db`) via `DB_PATH` env variable set by the test file.

## Development Patterns

- All imports use relative paths from project root
- `services/__init__.py` and `data/__init__.py` are empty modules
- Pydantic `LLMResponseSchema` validates LLM output before use
- Agent decisions are always persisted to `agent_actions` table
- Conversation history is stored as JSON in SQLite text fields
- The `generate_email_draft()` and `generate_broker_summary()` functions create formatted in-app drafts only — no external sending

## Known LSP Warnings

The LSP reports errors for `null`, `true`, `false` in `data/leads.py` and import issues in `services/` files. These are LSP configuration issues, not code bugs. The actual Python code is valid (uses `None`, `True`, `False` after `sed` fix).
