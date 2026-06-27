import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("YKL_DB_PATH", "ykl.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                url            TEXT NOT NULL,
                title          TEXT,
                channel        TEXT,
                duration       TEXT,
                topic          TEXT NOT NULL,
                subtopic       TEXT,
                summary        TEXT,
                key_points     TEXT,
                takeaways      TEXT,
                ai_opinion     TEXT,
                quotes         TEXT,
                model_used     TEXT,
                input_tokens   INTEGER DEFAULT 0,
                output_tokens  INTEGER DEFAULT 0,
                cost_usd       REAL DEFAULT 0,
                stock_analysis TEXT,
                synced_owui    INTEGER DEFAULT 0,
                created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migrate existing tables that predate new columns
        existing = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
        migrations = [
            ("input_tokens",   "INTEGER DEFAULT 0"),
            ("output_tokens",  "INTEGER DEFAULT 0"),
            ("cost_usd",       "REAL DEFAULT 0"),
            ("stock_analysis", "TEXT"),
            ("synced_owui",    "INTEGER DEFAULT 0"),
        ]
        for col, typedef in migrations:
            if col not in existing:
                conn.execute(f"ALTER TABLE entries ADD COLUMN {col} {typedef}")


def save_entry(entry: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO entries
                (url, title, channel, duration, topic, subtopic,
                 summary, key_points, takeaways, ai_opinion, quotes, model_used,
                 input_tokens, output_tokens, cost_usd, stock_analysis)
            VALUES
                (:url, :title, :channel, :duration, :topic, :subtopic,
                 :summary, :key_points, :takeaways, :ai_opinion, :quotes, :model_used,
                 :input_tokens, :output_tokens, :cost_usd, :stock_analysis)
            """,
            {
                **entry,
                "key_points":     json.dumps(entry.get("key_points") or []),
                "takeaways":      json.dumps(entry.get("takeaways") or []),
                "quotes":         json.dumps(entry.get("quotes") or []),
                "stock_analysis": json.dumps(entry.get("stock_analysis") or {}),
                "input_tokens":   entry.get("input_tokens") or 0,
                "output_tokens":  entry.get("output_tokens") or 0,
                "cost_usd":       entry.get("cost_usd") or 0.0,
            },
        )
        return cur.lastrowid


def mark_synced(entry_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE entries SET synced_owui=1 WHERE id=?", (entry_id,))


def get_entry(entry_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    return _deserialize(dict(row)) if row else None


def get_all_entries() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM entries ORDER BY id DESC").fetchall()
    return [_deserialize(dict(r)) for r in rows]


def _deserialize(row: dict) -> dict:
    for field in ("key_points", "takeaways", "quotes"):
        row[field] = json.loads(row[field] or "[]")
    row["stock_analysis"] = json.loads(row.get("stock_analysis") or "{}")
    return row
