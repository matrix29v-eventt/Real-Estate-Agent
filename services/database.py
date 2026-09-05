import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db"
    ),
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS properties (
        property_id TEXT PRIMARY KEY,
        name TEXT,
        location TEXT,
        property_type TEXT,
        bhk INTEGER,
        price INTEGER,
        sqft INTEGER,
        parking INTEGER,
        furnishing TEXT,
        amenities TEXT,
        availability TEXT,
        builder TEXT,
        possession_status TEXT,
        tags TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        lead_id TEXT PRIMARY KEY,
        name TEXT,
        original_inquiry TEXT,
        parsed_requirements TEXT,
        intent_score INTEGER,
        intent_tier TEXT,
        status TEXT,
        current_action TEXT,
        created_at TEXT,
        updated_at TEXT,
        conversation_history TEXT,
        decision_history TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        conversation_id TEXT PRIMARY KEY,
        lead_id TEXT,
        turn_number INTEGER,
        sender TEXT,
        message TEXT,
        timestamp TEXT,
        FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS agent_actions (
        action_id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id TEXT,
        timestamp TEXT,
        decision TEXT,
        reasoning TEXT,
        intent_score INTEGER,
        input_snapshot TEXT,
        output_snapshot TEXT,
        FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
    )""")
    conn.commit()
    conn.close()


def seed_data():
    init_db()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM properties")
    if c.fetchone()[0] == 0:
        from data.properties import PROPERTIES

        for p in PROPERTIES:
            c.execute(
                "INSERT OR IGNORE INTO properties VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    p["property_id"],
                    p["name"],
                    p["location"],
                    p["property_type"],
                    p["bhk"],
                    p["price"],
                    p["sqft"],
                    p["parking"],
                    p["furnishing"],
                    p["amenities"],
                    p["availability"],
                    p["builder"],
                    p["possession_status"],
                    p["tags"],
                    p["created_at"],
                ),
            )
    c.execute("SELECT COUNT(*) FROM leads")
    if c.fetchone()[0] == 0:
        from data.leads import SEED_LEADS

        for l in SEED_LEADS:
            c.execute(
                "INSERT OR IGNORE INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    l["lead_id"],
                    l["name"],
                    l["original_inquiry"],
                    json.dumps(l["parsed_requirements"]),
                    l["intent_score"],
                    l["intent_tier"],
                    l["status"],
                    l["current_action"],
                    l["created_at"],
                    l["updated_at"],
                    json.dumps(l["conversation_history"]),
                    json.dumps(l["decision_history"]),
                ),
            )
    conn.commit()
    conn.close()


def get_all_properties():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM properties")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_property_by_id(pid):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM properties WHERE property_id=?", (pid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def filter_properties(
    location=None,
    min_budget=None,
    max_budget=None,
    bhk=None,
    property_type=None,
    min_sqft=None,
    parking=None,
    furnishing=None,
):
    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM properties WHERE 1=1"
    params = []
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")
    if min_budget:
        query += " AND price >= ?"
        params.append(min_budget)
    if max_budget:
        query += " AND price <= ?"
        params.append(max_budget)
    if bhk:
        query += " AND bhk >= ?"
        params.append(bhk)
    if property_type:
        query += " AND property_type = ?"
        params.append(property_type)
    if min_sqft:
        query += " AND sqft >= ?"
        params.append(min_sqft)
    if parking:
        query += " AND parking >= ?"
        params.append(parking)
    if furnishing:
        query += " AND furnishing = ?"
        params.append(furnishing)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_leads():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM leads ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lead_by_id(lid):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE lead_id=?", (lid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def save_lead(lead_data):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            lead_data["lead_id"],
            lead_data["name"],
            lead_data["original_inquiry"],
            json.dumps(lead_data.get("parsed_requirements", {})),
            lead_data.get("intent_score", 0),
            lead_data.get("intent_tier", "UNKNOWN"),
            lead_data.get("status", "NEW"),
            lead_data.get("current_action", "ASK_MORE_INFO"),
            lead_data.get("created_at"),
            lead_data.get("updated_at"),
            json.dumps(lead_data.get("conversation_history", [])),
            json.dumps(lead_data.get("decision_history", [])),
        ),
    )
    conn.commit()
    conn.close()


def add_conversation(lead_id, sender, message, turn_number):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (lead_id, turn_number, sender, message, timestamp) VALUES (?,?,?,?,?)",
        (lead_id, turn_number, sender, message, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def add_agent_action(
    lead_id, decision, reasoning, intent_score, input_snapshot, output_snapshot
):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO agent_actions (lead_id, timestamp, decision, reasoning, intent_score, input_snapshot, output_snapshot) VALUES (?,?,?,?,?,?,?)",
        (
            lead_id,
            datetime.now().isoformat(),
            decision,
            json.dumps(reasoning),
            intent_score,
            json.dumps(input_snapshot),
            json.dumps(output_snapshot),
        ),
    )
    conn.commit()
    conn.close()
    return c.lastrowid


def get_actions_for_lead(lid):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_actions WHERE lead_id=? ORDER BY timestamp", (lid,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lead_metrics():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE intent_tier='HIGH'")
    high = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE intent_tier='MEDIUM'")
    medium = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE intent_tier='NEEDS_CLARIFICATION'")
    needs_clarification = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE current_action='ESCALATE_TO_BROKER'")
    escalated = c.fetchone()[0]
    c.execute(
        "SELECT COUNT(*) FROM leads WHERE current_action='LOW_PRIORITY_OR_DISCARD'"
    )
    low_priority = c.fetchone()[0]
    conn.close()
    return {
        "total": total,
        "high": high,
        "medium": medium,
        "needs_clarification": needs_clarification,
        "escalated": escalated,
        "low_priority": low_priority,
    }
