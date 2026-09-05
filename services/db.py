"""SQLite persistence: schema, seeding, CRUD and the decision audit trail.

Everything here is deterministic plumbing. No LLM calls live in this module.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional

import config
from models.schemas import LeadStatus, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    property_id       TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    location          TEXT NOT NULL,
    property_type     TEXT NOT NULL,
    bhk               INTEGER,
    price             INTEGER NOT NULL,
    sqft              INTEGER NOT NULL,
    parking           INTEGER NOT NULL DEFAULT 0,
    furnishing        TEXT,
    amenities         TEXT,
    availability      TEXT NOT NULL DEFAULT 'AVAILABLE',
    builder           TEXT,
    possession_status TEXT,
    possession_date   TEXT,
    tags              TEXT,
    created_at        TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    lead_id               TEXT PRIMARY KEY,
    name                  TEXT,
    contact               TEXT,
    original_inquiry      TEXT,
    requirements_json     TEXT NOT NULL DEFAULT '{}',
    intent_score          INTEGER DEFAULT 0,
    intent_tier           TEXT,
    status                TEXT NOT NULL DEFAULT 'NEW',
    current_action        TEXT,
    recommended_next_step TEXT,
    summary_json          TEXT,
    created_at            TEXT,
    updated_at            TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    turn_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id    TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    role       TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads (lead_id)
);

CREATE TABLE IF NOT EXISTS agent_actions (
    action_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    decision        TEXT NOT NULL,
    intent_score    INTEGER,
    intent_tier     TEXT,
    reasoning_json  TEXT,
    input_snapshot  TEXT,
    output_snapshot TEXT,
    status_before   TEXT,
    status_after    TEXT,
    llm_provider    TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads (lead_id)
);

CREATE INDEX IF NOT EXISTS idx_conv_lead ON conversations (lead_id);
CREATE INDEX IF NOT EXISTS idx_actions_lead ON agent_actions (lead_id);
"""


# --------------------------------------------------------------------------- #
# Connection handling
# --------------------------------------------------------------------------- #
def get_conn() -> sqlite3.Connection:
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    """Drop everything and rebuild. Used by tests and the UI reset button."""
    with connection() as conn:
        for table in ("agent_actions", "conversations", "leads", "properties"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
def seed_properties(rows: Iterable[Dict[str, Any]]) -> int:
    cols = (
        "property_id", "name", "location", "property_type", "bhk", "price", "sqft",
        "parking", "furnishing", "amenities", "availability", "builder",
        "possession_status", "possession_date", "tags", "created_at",
    )
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT OR REPLACE INTO properties ({', '.join(cols)}) VALUES ({placeholders})"
    payload = []
    for row in rows:
        record = dict(row)
        for key in ("amenities", "tags"):
            value = record.get(key)
            if isinstance(value, (list, tuple)):
                record[key] = ",".join(value)
        payload.append(tuple(record.get(c) for c in cols))
    with connection() as conn:
        conn.executemany(sql, payload)
    return len(payload)


def ensure_seeded(force: bool = False) -> Dict[str, int]:
    """Create the schema and load seed data when the tables are empty."""
    from data.lead_seed import seed_leads  # local import avoids a cycle
    from data.property_seed import property_rows

    init_db()
    counts = {"properties": 0, "leads": 0}
    if force or count_rows("properties") == 0:
        counts["properties"] = seed_properties(property_rows())
    if force or count_rows("leads") == 0:
        counts["leads"] = seed_leads()
    return counts


def count_rows(table: str) -> int:
    with connection() as conn:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.OperationalError:
            return 0


# --------------------------------------------------------------------------- #
# Properties
# --------------------------------------------------------------------------- #
def list_properties(only_available: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM properties"
    if only_available:
        sql += " WHERE availability = 'AVAILABLE'"
    with connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [_property_from_row(r) for r in rows]


def get_properties(ids: Iterable[str]) -> List[Dict[str, Any]]:
    ids = list(ids)
    if not ids:
        return []
    marks = ", ".join("?" for _ in ids)
    with connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM properties WHERE property_id IN ({marks})", ids
        ).fetchall()
    by_id = {r["property_id"]: _property_from_row(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def _property_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    record = dict(row)
    for key in ("amenities", "tags"):
        raw = record.get(key) or ""
        record[key] = [part.strip() for part in raw.split(",") if part.strip()]
    record["parking"] = bool(record.get("parking"))
    return record


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #
def next_lead_id() -> str:
    with connection() as conn:
        rows = conn.execute("SELECT lead_id FROM leads WHERE lead_id LIKE 'L%'").fetchall()
    numbers = []
    for row in rows:
        tail = str(row["lead_id"])[1:]
        if tail.isdigit():
            numbers.append(int(tail))
    return f"L{(max(numbers) + 1) if numbers else 1:03d}"


def create_lead(
    lead_id: Optional[str] = None,
    name: Optional[str] = None,
    contact: Optional[str] = None,
    original_inquiry: str = "",
    requirements: Optional[Dict[str, Any]] = None,
    status: str = LeadStatus.NEW.value,
    created_at: Optional[str] = None,
) -> str:
    lead_id = lead_id or next_lead_id()
    now = created_at or utc_now()
    with connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO leads
               (lead_id, name, contact, original_inquiry, requirements_json,
                intent_score, intent_tier, status, current_action,
                recommended_next_step, summary_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL, NULL, ?, ?)""",
            (lead_id, name, contact, original_inquiry,
             json.dumps(requirements or {}), status, now, now),
        )
    return lead_id


def update_lead(lead_id: str, **fields: Any) -> None:
    """Update whitelisted lead columns. ``requirements``/``summary`` may be dicts."""
    mapping = {
        "name": "name",
        "contact": "contact",
        "original_inquiry": "original_inquiry",
        "requirements": "requirements_json",
        "intent_score": "intent_score",
        "intent_tier": "intent_tier",
        "status": "status",
        "current_action": "current_action",
        "recommended_next_step": "recommended_next_step",
        "summary": "summary_json",
    }
    assignments, values = [], []
    for key, value in fields.items():
        column = mapping.get(key)
        if column is None:
            continue
        if column.endswith("_json") and not isinstance(value, str):
            value = json.dumps(value)
        assignments.append(f"{column} = ?")
        values.append(value)
    if not assignments:
        return
    assignments.append("updated_at = ?")
    values.extend([utc_now(), lead_id])
    with connection() as conn:
        conn.execute(f"UPDATE leads SET {', '.join(assignments)} WHERE lead_id = ?", values)


def get_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    return _lead_from_row(row) if row else None


def list_leads() -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY updated_at DESC").fetchall()
    return [_lead_from_row(r) for r in rows]


def delete_lead(lead_id: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM agent_actions WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM conversations WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM leads WHERE lead_id = ?", (lead_id,))


def _lead_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    record = dict(row)
    record["requirements"] = _loads(record.pop("requirements_json", "{}"), {})
    record["summary"] = _loads(record.pop("summary_json", None), None)
    return record


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #
def add_turn(lead_id: str, role: str, message: str, created_at: Optional[str] = None) -> int:
    with connection() as conn:
        index = conn.execute(
            "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM conversations WHERE lead_id = ?",
            (lead_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO conversations (lead_id, turn_index, role, message, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (lead_id, index, role, message, created_at or utc_now()),
        )
    return int(cur.lastrowid)


def get_turns(lead_id: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE lead_id = ? ORDER BY turn_index",
            (lead_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def buyer_turn_count(lead_id: str) -> int:
    with connection() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE lead_id = ? AND role = 'buyer'",
                (lead_id,),
            ).fetchone()[0]
        )


# --------------------------------------------------------------------------- #
# Agent action audit trail
# --------------------------------------------------------------------------- #
def record_action(
    lead_id: str,
    decision: str,
    intent_score: int,
    intent_tier: str,
    reasoning: Any,
    input_snapshot: Any,
    output_snapshot: Any,
    status_before: Optional[str],
    status_after: str,
    llm_provider: str = "",
    timestamp: Optional[str] = None,
) -> int:
    with connection() as conn:
        cur = conn.execute(
            """INSERT INTO agent_actions
               (lead_id, timestamp, decision, intent_score, intent_tier, reasoning_json,
                input_snapshot, output_snapshot, status_before, status_after, llm_provider)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead_id,
                timestamp or utc_now(),
                decision,
                int(intent_score),
                intent_tier,
                json.dumps(reasoning),
                json.dumps(input_snapshot, default=str),
                json.dumps(output_snapshot, default=str),
                status_before,
                status_after,
                llm_provider,
            ),
        )
    return int(cur.lastrowid)


def get_actions(lead_id: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM agent_actions"
    params: tuple = ()
    if lead_id:
        sql += " WHERE lead_id = ?"
        params = (lead_id,)
    sql += " ORDER BY action_id DESC"
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for row in rows:
        record = dict(row)
        record["reasoning"] = _loads(record.pop("reasoning_json", "[]"), [])
        record["input_snapshot"] = _loads(record.get("input_snapshot"), {})
        record["output_snapshot"] = _loads(record.get("output_snapshot"), {})
        out.append(record)
    return out


# --------------------------------------------------------------------------- #
# Dashboard aggregates
# --------------------------------------------------------------------------- #
def dashboard_metrics() -> Dict[str, int]:
    leads = list_leads()
    tiers = [(lead.get("intent_tier") or "") for lead in leads]
    statuses = [(lead.get("status") or "") for lead in leads]
    return {
        "total_leads": len(leads),
        "high_intent": tiers.count("HIGH"),
        "medium_intent": tiers.count("MEDIUM"),
        "low_intent": tiers.count("LOW"),
        "needs_clarification": tiers.count("NEEDS_CLARIFICATION"),
        "broker_escalations": statuses.count(LeadStatus.BROKER_ESCALATION.value),
        "low_priority": statuses.count(LeadStatus.LOW_PRIORITY.value),
        "nurturing": statuses.count(LeadStatus.NURTURING.value),
        "decisions_logged": count_rows("agent_actions"),
    }


def _loads(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
