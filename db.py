import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("YKL_DB_PATH", "ykl.db"))


def get_conn() -> sqlite3.Connection:
    """Get a database connection with row factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT NOT NULL,
                title       TEXT,
                channel     TEXT,
                duration    TEXT,
                topic       TEXT NOT NULL,
                subtopic    TEXT,
                summary     TEXT,
                key_points  TEXT,
                takeaways   TEXT,
                ai_opinion  TEXT,
                quotes      TEXT,
                model_used  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_entry(entry: dict) -> int:
    """Persist a reviewed entry. Returns new row id."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO entries
                (url, title, channel, duration, topic, subtopic,
                 summary, key_points, takeaways, ai_opinion, quotes, model_used)
            VALUES
                (:url, :title, :channel, :duration, :topic, :subtopic,
                 :summary, :key_points, :takeaways, :ai_opinion, :quotes, :model_used)
            """,
            {
                **entry,
                "key_points": json.dumps(entry.get("key_points") or []),
                "takeaways":  json.dumps(entry.get("takeaways") or []),
                "quotes":     json.dumps(entry.get("quotes") or []),
            },
        )
        return cur.lastrowid


def get_all_entries() -> list[dict]:
    """Return all saved entries, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY id DESC"
        ).fetchall()
    return [_deserialize(dict(r)) for r in rows]


def _deserialize(row: dict) -> dict:
    """Deserialize JSON fields from storage to Python objects."""
    for field in ("key_points", "takeaways", "quotes"):
        row[field] = json.loads(row[field] or "[]")
    return row
