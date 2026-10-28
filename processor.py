import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

import llm

DB_PATH = Path(os.getenv("YKL_DB_PATH", "ykl.db"))
_lock = threading.Lock()
_llm_sem = threading.Semaphore(int(os.getenv("YKL_MAX_CONCURRENT", "2")))

TERMINAL_STATES = ("done", "failed")
IN_PROGRESS_STATES = (
    "pending",
    "fetching_transcript",
    "fetching_metadata",
    "summarizing",
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_jobs_table() -> None:
    """Create persistent jobs table if missing."""
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id     TEXT PRIMARY KEY,
                status     TEXT NOT NULL,
                url        TEXT NOT NULL,
                mode       TEXT NOT NULL,
                result     TEXT,
                error      TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def resume_pending() -> None:
    """Mark orphaned in-progress jobs as failed on startup so user can Retry."""
    placeholders = ",".join("?" * len(IN_PROGRESS_STATES))
    with _conn() as conn:
        conn.execute(
            f"UPDATE jobs SET status='failed', error='Server restarted mid-processing. Click Retry.' "
            f"WHERE status IN ({placeholders})",
            IN_PROGRESS_STATES,
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["job_id"] = d.get("job_id")
    if d.get("result"):
        d["result"] = json.loads(d["result"])
    else:
        d["result"] = None
    return d


def submit(urls: list[str], mode: str) -> list[str]:
    """Queue URLs for processing. Returns list of job IDs."""
    if mode not in ("fast", "quality"):
        raise ValueError(f"mode must be 'fast' or 'quality', got {mode!r}")
    job_ids = []
    for url in urls:
        job_id = str(uuid.uuid4())
        with _lock, _conn() as conn:
            conn.execute(
                "INSERT INTO jobs(job_id, status, url, mode) VALUES(?, ?, ?, ?)",
                (job_id, "pending", url, mode),
            )
        t = threading.Thread(target=_process, args=(job_id, url, mode), daemon=True)
        t.start()
        job_ids.append(job_id)
    return job_ids


def get_job(job_id: str) -> dict | None:
    """Return job dict or None if not found."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_queue() -> list[dict]:
    """Return all jobs (in-progress + done + failed) not yet saved/discarded."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_queue_count() -> int:
    """Count of jobs awaiting user review (done or failed)."""
    placeholders = ",".join("?" * len(TERMINAL_STATES))
    with _conn() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})",
            TERMINAL_STATES,
        ).fetchone()
    return row[0] if row else 0


def remove_job(job_id: str) -> None:
    """Delete job from the store (after save or discard)."""
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))


def requeue(job_id: str) -> None:
    """Reset a failed job to pending and reprocess."""
    job = get_job(job_id)
    if not job:
        return
    url = job["url"]
    mode = job["mode"]
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='pending', result=NULL, error=NULL WHERE job_id=?",
            (job_id,),
        )
    t = threading.Thread(target=_process, args=(job_id, url, mode), daemon=True)
    t.start()


def _process(job_id: str, url: str, mode: str) -> None:
    """Background worker: transcript → metadata → LLM → persist result."""
    if not get_job(job_id):
        return
    _set_status(job_id, "fetching_transcript")
    try:
        video_id = _extract_video_id(url)
        fetched = YouTubeTranscriptApi().fetch(video_id)
        transcript = " ".join(t.text for t in fetched)
    except (TranscriptsDisabled, NoTranscriptFound):
        _fail(job_id, "No transcript available for this video.")
        return
    except Exception as e:
        _fail(job_id, f"Transcript fetch failed: {e}")
        return

    _set_status(job_id, "fetching_metadata")
    title, channel = _fetch_metadata(url)
    word_count = len(transcript.split())
    duration = f"~{max(1, round(word_count / 130))} min"

    _set_status(job_id, "summarizing")
    last_error = "Unknown error"
    for attempt in range(3):
        try:
            with _llm_sem:
                result, model_used = llm.summarize(transcript, mode)
            result.update(
                {
                    "url": url,
                    "title": title,
                    "channel": channel,
                    "duration": duration,
                    "model_used": model_used,
                }
            )
            with _lock, _conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status='done', result=? WHERE job_id=?",
                    (json.dumps(result), job_id),
                )
            return
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                time.sleep(10)

    _fail(job_id, f"Summarization failed: {last_error}")


def _fetch_metadata(url: str) -> tuple[str, str]:
    """Fetch title and channel via noembed. Returns ('Unknown', 'Unknown') on failure."""
    try:
        resp = requests.get(f"https://noembed.com/embed?url={url}", timeout=10)
        data = resp.json()
        return data.get("title", "Unknown"), data.get("author_name", "Unknown")
    except Exception:
        return "Unknown", "Unknown"


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from standard or short URL."""
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be",):
        vid = parsed.path.lstrip("/")
        if vid:
            return vid
    qs = parse_qs(parsed.query)
    vid = qs.get("v", [None])[0]
    if vid:
        return vid
    raise ValueError(f"Cannot extract video ID from: {url}")


def _set_status(job_id: str, status: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status=? WHERE job_id=?", (status, job_id)
        )


def _fail(job_id: str, error: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', error=? WHERE job_id=?",
            (error, job_id),
        )
