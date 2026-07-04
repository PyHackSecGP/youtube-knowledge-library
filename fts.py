"""FTS5 search and lesson selection across ykl.db."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("YKL_DB_PATH", "ykl.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_fts() -> None:
    """Add FTS5 table + lesson_sent_at column. Safe to call on every startup."""
    with get_conn() as conn:
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
        if "lesson_sent_at" not in existing_cols:
            conn.execute("ALTER TABLE entries ADD COLUMN lesson_sent_at DATETIME")

        # Standalone FTS5 (no content= linkage — simpler, always in sync via triggers)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                entry_id UNINDEXED,
                title, summary, key_points, takeaways, ai_opinion,
                tokenize='unicode61'
            )
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                INSERT INTO entries_fts(entry_id, title, summary, key_points, takeaways, ai_opinion)
                VALUES (new.id, new.title, new.summary, new.key_points, new.takeaways, new.ai_opinion);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                DELETE FROM entries_fts WHERE entry_id = old.id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                DELETE FROM entries_fts WHERE entry_id = old.id;
                INSERT INTO entries_fts(entry_id, title, summary, key_points, takeaways, ai_opinion)
                VALUES (new.id, new.title, new.summary, new.key_points, new.takeaways, new.ai_opinion);
            END
        """)

        # Populate from existing rows if FTS table is empty
        fts_count = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
        if fts_count == 0:
            conn.execute("""
                INSERT INTO entries_fts(entry_id, title, summary, key_points, takeaways, ai_opinion)
                SELECT id, title, summary, key_points, takeaways, ai_opinion FROM entries
            """)


def search(query: str, limit: int = 5) -> list[dict]:
    """FTS5 search. Returns entries sorted by relevance (best match first)."""
    with get_conn() as conn:
        try:
            rows = conn.execute("""
                SELECT e.*, bm25(entries_fts) AS rank
                FROM entries_fts
                JOIN entries e ON e.id = entries_fts.entry_id
                WHERE entries_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [_deserialize(dict(r)) for r in rows]


def get_lesson_candidate() -> dict | None:
    """Return an entry not sent as lesson in the last 30 days (random pick)."""
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM entries
            WHERE lesson_sent_at IS NULL OR lesson_sent_at < ?
            ORDER BY RANDOM()
            LIMIT 1
        """, (cutoff,)).fetchone()
    return _deserialize(dict(row)) if row else None


def mark_lesson_sent(entry_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE entries SET lesson_sent_at = ? WHERE id = ?",
            (datetime.now().isoformat(), entry_id),
        )


def get_tree() -> dict[str, dict[str, int]]:
    """Return {topic: {subtopic: count}} for the knowledge tree."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT topic, subtopic, COUNT(*) AS cnt FROM entries GROUP BY topic, subtopic"
        ).fetchall()
    tree: dict[str, dict[str, int]] = {}
    for row in rows:
        topic = row["topic"] or "Uncategorized"
        sub = row["subtopic"] or "General"
        tree.setdefault(topic, {})[sub] = row["cnt"]
    return tree


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        topics = conn.execute("SELECT COUNT(DISTINCT topic) FROM entries").fetchone()[0]
        lessons = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE lesson_sent_at IS NOT NULL"
        ).fetchone()[0]
    return {"total_videos": total, "topics": topics, "lessons_sent": lessons}


def _deserialize(row: dict) -> dict:
    for field in ("key_points", "takeaways", "quotes"):
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field] or "[]")
    if isinstance(row.get("stock_analysis"), str):
        row["stock_analysis"] = json.loads(row.get("stock_analysis") or "{}")
    return row
