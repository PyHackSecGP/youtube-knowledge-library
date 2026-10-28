"""Weekly YKL digest → Telegram.

Pulls entries from last 7 days, formats a per-topic digest, sends via Telegram
Bot API. Run via systemd timer (youtube-digest.timer) or manually:

    venv/bin/python digest.py              # last 7 days
    venv/bin/python digest.py --days 1     # yesterday only
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("YKL_DB_PATH", Path(__file__).parent / "ykl.db"))
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def fetch(days: int) -> list[sqlite3.Row]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, channel, topic, subtopic, duration, cost_usd, created_at, url "
        "FROM entries WHERE created_at >= ? ORDER BY topic, created_at DESC",
        (cutoff,),
    ).fetchall()
    conn.close()
    return rows


def format_digest(rows: list[sqlite3.Row], days: int) -> str:
    if not rows:
        return f"<b>YKL digest</b> — no videos saved in the last {days} day(s)."
    by_topic: dict[str, list[sqlite3.Row]] = {}
    total_cost = 0.0
    for r in rows:
        by_topic.setdefault(r["topic"] or "Uncategorized", []).append(r)
        total_cost += r["cost_usd"] or 0.0
    lines = [
        f"<b>📚 YKL weekly digest</b> — {len(rows)} video(s), ${total_cost:.4f} spent",
        f"<i>Last {days} day(s), {datetime.now():%Y-%m-%d}</i>",
        "",
    ]
    for topic, entries in by_topic.items():
        lines.append(f"<b>{topic}</b> ({len(entries)})")
        for e in entries[:10]:
            title = (e["title"] or e["url"])[:80]
            sub = f" · {e['subtopic']}" if e["subtopic"] else ""
            lines.append(f"• {title}{sub}")
        if len(entries) > 10:
            lines.append(f"  … and {len(entries) - 10} more")
        lines.append("")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    if not TOKEN or not CHAT_ID:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing — skipping send", flush=True)
        return False
    resp = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"telegram send failed: {resp.status_code} {resp.text}", flush=True)
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = fetch(args.days)
    text = format_digest(rows, args.days)
    if args.dry_run:
        print(text)
        return
    ok = send_telegram(text)
    print(f"digest sent: {ok}, {len(rows)} entries", flush=True)


if __name__ == "__main__":
    main()
