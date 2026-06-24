# YouTube Knowledge Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask web app that converts YouTube URLs into AI-generated structured summaries, saved to a topic-organized knowledge library.

**Architecture:** Single Flask app with background thread processing and JS polling for async UX. Claude Haiku API (primary/fast) or Ollama cascade (quality/overnight) for summarization. SQLite persistence. In-memory job store for unreviewed entries.

**Tech Stack:** Python 3.11+, Flask 3.x, youtube-transcript-api, anthropic SDK, requests, SQLite, Vanilla JS

---

## File Map

| File | Responsibility |
|------|---------------|
| `db.py` | SQLite schema init, save/retrieve entries |
| `llm.py` | LLM abstraction: Claude API + Ollama cascade with timeout/fallback |
| `processor.py` | Background pipeline: transcript → metadata → LLM → job store |
| `app.py` | Flask routes, context processors |
| `templates/base.html` | Nav bar, dark terminal theme, shared layout |
| `templates/process.html` | Screen 1 (URL form) + Screen 2 (processing status) |
| `templates/queue.html` | Screen 3: Review Queue with expand/save/discard |
| `templates/library.html` | Screen 4: card grid grouped by topic |
| `static/app.js` | JS polling, expand/collapse, badge updates |
| `tests/conftest.py` | pytest path setup |
| `tests/test_db.py` | DB layer tests |
| `tests/test_llm.py` | LLM cascade/fallback tests |
| `tests/test_processor.py` | Pipeline unit tests |
| `tests/test_app.py` | Route integration tests |

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `static/.gitkeep`
- Create: `templates/.gitkeep`

- [ ] **Step 1: Create requirements.txt**

```
flask>=3.0
youtube-transcript-api>=0.6
anthropic>=0.25
requests>=2.31
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 2: Create .env.example**

```
ANTHROPIC_API_KEY=your-key-here
```

- [ ] **Step 3: Create pytest.ini**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: Create tests/conftest.py**

```python
# ensures project root is on sys.path for all tests
```

- [ ] **Step 5: Create directories and install**

```bash
mkdir -p templates static tests
touch static/.gitkeep templates/.gitkeep
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example pytest.ini tests/conftest.py
git commit -m "chore: project scaffold"
```

---

## Task 2: Database Layer

**Files:**
- Create: `tests/test_db.py`
- Create: `db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_db.py`:

```python
import pytest
import db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


def test_save_entry_returns_id():
    entry = {
        "url": "https://youtube.com/watch?v=test",
        "title": "Test Video",
        "channel": "Test Channel",
        "duration": "~10 min",
        "topic": "Cybersecurity",
        "subtopic": "Malware Analysis",
        "summary": "Test summary",
        "key_points": ["point 1", "point 2"],
        "takeaways": ["do this"],
        "ai_opinion": "interesting",
        "quotes": ["notable quote"],
        "model_used": "claude-haiku-4-5",
    }
    entry_id = db.save_entry(entry)
    assert isinstance(entry_id, int)
    assert entry_id >= 1


def test_get_all_entries_returns_saved():
    entry = {
        "url": "https://youtube.com/watch?v=test",
        "title": "Test Video",
        "channel": "Test Channel",
        "duration": "~10 min",
        "topic": "Cybersecurity",
        "subtopic": "Malware Analysis",
        "summary": "Test summary",
        "key_points": ["point 1"],
        "takeaways": ["takeaway"],
        "ai_opinion": "good",
        "quotes": ["quote"],
        "model_used": "claude-haiku-4-5",
    }
    db.save_entry(entry)
    entries = db.get_all_entries()
    assert len(entries) == 1
    assert entries[0]["title"] == "Test Video"
    assert entries[0]["topic"] == "Cybersecurity"


def test_json_fields_deserialize_to_lists():
    entry = {
        "url": "https://youtube.com/watch?v=test2",
        "title": "T2", "channel": "C", "duration": "~5 min",
        "topic": "Investing", "subtopic": "ETFs",
        "summary": "s", "key_points": ["a", "b"],
        "takeaways": ["x"], "ai_opinion": "y",
        "quotes": ["q1", "q2"], "model_used": "qwen3.5:latest",
    }
    db.save_entry(entry)
    entries = db.get_all_entries()
    assert entries[0]["key_points"] == ["a", "b"]
    assert entries[0]["quotes"] == ["q1", "q2"]


def test_get_all_entries_empty_db():
    assert db.get_all_entries() == []


def test_multiple_entries_ordered_newest_first():
    for i in range(3):
        db.save_entry({
            "url": f"https://youtube.com/watch?v={i}",
            "title": f"Video {i}", "channel": "C", "duration": "~1 min",
            "topic": "Cybersecurity", "subtopic": "Sub",
            "summary": "s", "key_points": [], "takeaways": [],
            "ai_opinion": "ok", "quotes": [], "model_used": "llama3.2:3b",
        })
    entries = db.get_all_entries()
    assert len(entries) == 3
    assert entries[0]["title"] == "Video 2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implement db.py**

```python
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
            "SELECT * FROM entries ORDER BY created_at DESC"
        ).fetchall()
    return [_deserialize(dict(r)) for r in rows]


def _deserialize(row: dict) -> dict:
    for field in ("key_points", "takeaways", "quotes"):
        row[field] = json.loads(row[field] or "[]")
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add database layer with SQLite persistence"
```

---

## Task 3: LLM Abstraction

**Files:**
- Create: `tests/test_llm.py`
- Create: `llm.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
import llm

SAMPLE_RESULT = {
    "summary": "Test summary.",
    "key_points": ["point 1"],
    "takeaways": ["do this"],
    "ai_opinion": "Good video.",
    "quotes": ["a quote"],
    "topic": "Cybersecurity",
    "subtopic": "Malware Analysis",
}


def test_fast_mode_uses_claude_when_api_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("llm._claude", return_value=SAMPLE_RESULT) as mock_claude:
        result, model = llm.summarize("transcript text", "fast")
    mock_claude.assert_called_once()
    assert model == "claude-haiku-4-5"
    assert result["topic"] == "Cybersecurity"


def test_fast_mode_skips_claude_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("llm._ollama", return_value=SAMPLE_RESULT) as mock_ollama:
        result, model = llm.summarize("transcript text", "fast")
    first_call_model = mock_ollama.call_args[0][1]
    assert first_call_model == "qwen3.5:latest"
    assert model == "qwen3.5:latest"


def test_fast_mode_falls_back_to_ollama_when_claude_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("llm._claude", side_effect=RuntimeError("API error")):
        with patch("llm._ollama", return_value=SAMPLE_RESULT) as mock_ollama:
            result, model = llm.summarize("transcript text", "fast")
    assert model == "qwen3.5:latest"


def test_quality_mode_uses_hermes_first():
    with patch("llm._ollama", return_value=SAMPLE_RESULT) as mock_ollama:
        result, model = llm.summarize("transcript text", "quality")
    first_call_model = mock_ollama.call_args[0][1]
    assert first_call_model == "hermes3:70b"
    assert model == "hermes3:70b"


def test_cascades_to_smaller_model_on_timeout(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    call_count = {"n": 0}

    def mock_ollama(prompt, model, timeout):
        call_count["n"] += 1
        if model == "qwen3.5:latest":
            raise RuntimeError("timeout")
        return SAMPLE_RESULT

    with patch("llm._ollama", side_effect=mock_ollama):
        result, model = llm.summarize("transcript text", "fast")

    assert model == "llama3.2:3b"
    assert call_count["n"] == 2


def test_raises_when_all_models_fail(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("llm._ollama", side_effect=RuntimeError("all fail")):
        with pytest.raises(RuntimeError, match="All models failed"):
            llm.summarize("transcript text", "fast")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_llm.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm'`

- [ ] **Step 3: Implement llm.py**

```python
import json
import os

import requests
from anthropic import Anthropic

OLLAMA_URL = "http://100.126.22.55:11434"

PROMPT_TEMPLATE = """You are a knowledge extraction assistant. Given this YouTube transcript, return a JSON object with exactly these keys:

- "summary": string, 2-3 paragraphs
- "key_points": array of strings
- "takeaways": array of actionable strings
- "ai_opinion": string, your commentary and analysis
- "quotes": array of notable direct quote strings from the transcript
- "topic": one of ["Cybersecurity", "Investing", "World Events", "Personal Development"]
- "subtopic": string, specific sub-category (e.g. "Malware Analysis", "Index Funds", "Geopolitics")

Transcript: {transcript}"""

# (model, timeout_seconds)
_QUALITY_MODELS = [
    ("hermes3:70b",     1800),
    ("qwen3.5:latest",   600),
    ("llama3.2:3b",      300),
]

_FAST_MODELS = [
    ("qwen3.5:latest",   600),
    ("llama3.2:3b",      300),
]


def summarize(transcript: str, mode: str) -> tuple[dict, str]:
    """Summarize transcript. Returns (result_dict, model_name_used).

    Raises RuntimeError if all models fail.
    """
    prompt = PROMPT_TEMPLATE.format(transcript=transcript)

    if mode == "fast":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                return _claude(prompt, api_key), "claude-haiku-4-5"
            except Exception:
                pass
        models = _FAST_MODELS
    else:
        models = _QUALITY_MODELS

    for model, timeout in models:
        try:
            return _ollama(prompt, model, timeout), model
        except Exception:
            continue

    raise RuntimeError("All models failed")


def _claude(prompt: str, api_key: str, timeout: int = 60) -> dict:
    """Call Claude Haiku and parse JSON response."""
    client = Anthropic(api_key=api_key, timeout=timeout)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system="Return only valid JSON, no markdown code fences, no explanation.",
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(msg.content[0].text)


def _ollama(prompt: str, model: str, timeout: int) -> dict:
    """Call Ollama with JSON format enforced."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": model, "prompt": prompt, "format": "json", "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["response"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_llm.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add llm.py tests/test_llm.py
git commit -m "feat: add LLM abstraction with Claude/Ollama cascade"
```

---

## Task 4: Processing Pipeline

**Files:**
- Create: `tests/test_processor.py`
- Create: `processor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_processor.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
import processor


def test_submit_returns_one_job_id_per_url():
    with patch("processor.threading.Thread"):
        ids = processor.submit(["https://youtube.com/watch?v=abc"], "fast")
    assert len(ids) == 1
    assert processor.get_job(ids[0]) is not None


def test_submit_multiple_urls_returns_multiple_ids():
    with patch("processor.threading.Thread"):
        ids = processor.submit([
            "https://youtube.com/watch?v=abc",
            "https://youtube.com/watch?v=def",
        ], "fast")
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_get_job_returns_none_for_unknown_id():
    assert processor.get_job("nonexistent-id-xyz") is None


def test_remove_job_clears_entry():
    with patch("processor.threading.Thread"):
        ids = processor.submit(["https://youtube.com/watch?v=abc"], "fast")
    processor.remove_job(ids[0])
    assert processor.get_job(ids[0]) is None


def test_extract_video_id_standard_url():
    vid = processor._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert vid == "dQw4w9WgXcQ"


def test_extract_video_id_short_url():
    vid = processor._extract_video_id("https://youtu.be/dQw4w9WgXcQ")
    assert vid == "dQw4w9WgXcQ"


def test_extract_video_id_invalid_raises():
    with pytest.raises(ValueError):
        processor._extract_video_id("https://example.com/not-youtube")


def test_get_queue_returns_done_and_failed_jobs():
    processor.jobs.clear()
    processor.jobs["job-done"] = {"status": "done", "url": "u1", "mode": "fast", "result": {}, "error": None}
    processor.jobs["job-failed"] = {"status": "failed", "url": "u2", "mode": "fast", "result": None, "error": "err"}
    processor.jobs["job-pending"] = {"status": "pending", "url": "u3", "mode": "fast", "result": None, "error": None}
    queue = processor.get_queue()
    job_ids_in_queue = [item["job_id"] for item in queue]
    assert "job-done" in job_ids_in_queue
    assert "job-failed" in job_ids_in_queue
    assert "job-pending" not in job_ids_in_queue
    processor.jobs.clear()


def test_get_queue_count():
    processor.jobs.clear()
    processor.jobs["a"] = {"status": "done", "url": "u", "mode": "fast", "result": {}, "error": None}
    processor.jobs["b"] = {"status": "failed", "url": "u", "mode": "fast", "result": None, "error": "e"}
    processor.jobs["c"] = {"status": "pending", "url": "u", "mode": "fast", "result": None, "error": None}
    assert processor.get_queue_count() == 2
    processor.jobs.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_processor.py -v
```

Expected: `ModuleNotFoundError: No module named 'processor'`

- [ ] **Step 3: Implement processor.py**

```python
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

import llm

# In-memory job store. Keys are job_id strings.
# Each value: {status, url, mode, result, error}
jobs: dict[str, dict] = {}
_lock = threading.Lock()


def submit(urls: list[str], mode: str) -> list[str]:
    """Queue URLs for processing. Returns list of job IDs."""
    job_ids = []
    for url in urls:
        job_id = str(uuid.uuid4())
        with _lock:
            jobs[job_id] = {
                "status": "pending",
                "url": url,
                "mode": mode,
                "result": None,
                "error": None,
            }
        t = threading.Thread(target=_process, args=(job_id, url, mode), daemon=True)
        t.start()
        job_ids.append(job_id)
    return job_ids


def get_job(job_id: str) -> dict | None:
    """Return job dict or None if not found."""
    with _lock:
        return jobs.get(job_id)


def get_queue() -> list[dict]:
    """Return all done/failed jobs not yet saved/discarded."""
    with _lock:
        return [
            {"job_id": k, **v}
            for k, v in jobs.items()
            if v["status"] in ("done", "failed")
        ]


def get_queue_count() -> int:
    """Return count of jobs awaiting review."""
    with _lock:
        return sum(1 for v in jobs.values() if v["status"] in ("done", "failed"))


def remove_job(job_id: str) -> None:
    """Remove a job from the store (after save or discard)."""
    with _lock:
        jobs.pop(job_id, None)


def requeue(job_id: str) -> None:
    """Reset a failed job and reprocess it."""
    with _lock:
        job = jobs.get(job_id)
        if not job:
            return
        url = job["url"]
        mode = job["mode"]
        jobs[job_id] = {
            "status": "pending",
            "url": url,
            "mode": mode,
            "result": None,
            "error": None,
        }
    t = threading.Thread(target=_process, args=(job_id, url, mode), daemon=True)
    t.start()


def _process(job_id: str, url: str, mode: str) -> None:
    """Background worker: transcript → metadata → LLM → store result."""
    _set(job_id, "status", "fetching_transcript")
    try:
        video_id = _extract_video_id(url)
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = " ".join(t["text"] for t in transcript_list)
    except (TranscriptsDisabled, NoTranscriptFound):
        _fail(job_id, "No transcript available for this video.")
        return
    except Exception as e:
        _fail(job_id, f"Transcript fetch failed: {e}")
        return

    _set(job_id, "status", "fetching_metadata")
    title, channel = _fetch_metadata(url)
    word_count = len(transcript.split())
    duration = f"~{max(1, round(word_count / 130))} min"

    _set(job_id, "status", "summarizing")
    last_error = "Unknown error"
    for attempt in range(3):
        try:
            result, model_used = llm.summarize(transcript, mode)
            result.update({
                "url": url,
                "title": title,
                "channel": channel,
                "duration": duration,
                "model_used": model_used,
            })
            with _lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["result"] = result
            return
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                time.sleep(10)

    _fail(job_id, f"Summarization failed: {last_error}")


def _fetch_metadata(url: str) -> tuple[str, str]:
    """Fetch title and channel via noembed. Returns ('Unknown', 'Unknown') on failure."""
    try:
        resp = requests.get(
            f"https://noembed.com/embed?url={url}", timeout=10
        )
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


def _set(job_id: str, key: str, value) -> None:
    with _lock:
        if job_id in jobs:
            jobs[job_id][key] = value


def _fail(job_id: str, error: str) -> None:
    with _lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = error
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_processor.py -v
```

Expected: 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add processor.py tests/test_processor.py
git commit -m "feat: add background processing pipeline with job store"
```

---

## Task 5: Flask Routes

**Files:**
- Create: `tests/test_app.py`
- Create: `app.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_app.py`:

```python
import pytest
from unittest.mock import patch
import db
import processor
import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_process_redirects_on_empty_urls(client):
    resp = client.post("/process", data={"urls": "   \n  ", "mode": "fast"})
    assert resp.status_code == 302


def test_process_starts_jobs_and_renders_status(client):
    with patch("processor.submit", return_value=["job-abc"]) as mock_sub:
        resp = client.post("/process", data={
            "urls": "https://youtube.com/watch?v=abc",
            "mode": "fast",
        })
    assert resp.status_code == 200
    mock_sub.assert_called_once_with(["https://youtube.com/watch?v=abc"], "fast")
    assert b"job-abc" in resp.data


def test_status_returns_job_data(client):
    processor.jobs["test-job"] = {
        "status": "done", "url": "u", "mode": "fast",
        "result": {"title": "T"}, "error": None,
    }
    resp = client.get("/status/test-job")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "done"
    processor.jobs.pop("test-job", None)


def test_status_404_for_unknown_job(client):
    resp = client.get("/status/no-such-job-xyz")
    assert resp.status_code == 404


def test_queue_returns_200(client):
    resp = client.get("/queue")
    assert resp.status_code == 200


def test_library_returns_200(client):
    resp = client.get("/library")
    assert resp.status_code == 200


def test_discard_removes_job_and_redirects(client):
    processor.jobs["discard-job"] = {
        "status": "done", "url": "u", "mode": "fast",
        "result": {}, "error": None,
    }
    resp = client.post("/discard", data={"job_id": "discard-job"})
    assert resp.status_code == 302
    assert processor.get_job("discard-job") is None


def test_retry_requeues_failed_job(client):
    processor.jobs["retry-job"] = {
        "status": "failed", "url": "https://youtube.com/watch?v=x",
        "mode": "fast", "result": None, "error": "timeout",
    }
    with patch("processor.threading.Thread"):
        resp = client.post("/retry", data={"job_id": "retry-job"})
    assert resp.status_code == 302
    job = processor.get_job("retry-job")
    assert job["status"] == "pending"
    processor.jobs.pop("retry-job", None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_app.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Implement app.py**

```python
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

import db
import processor

load_dotenv()

app = Flask(__name__)

TOPICS = ["Cybersecurity", "Investing", "World Events", "Personal Development"]


@app.context_processor
def inject_globals() -> dict:
    return {
        "queue_count": processor.get_queue_count(),
        "topics": TOPICS,
    }


@app.route("/")
def index():
    return render_template("process.html")


@app.route("/process", methods=["POST"])
def process():
    raw = request.form.get("urls", "")
    urls = [u.strip() for u in raw.splitlines() if u.strip()]
    mode = request.form.get("mode", "fast")
    if not urls:
        return redirect(url_for("index"))
    job_ids = processor.submit(urls, mode)
    return render_template("process.html", job_ids=job_ids)


@app.route("/status/<job_id>")
def status(job_id: str):
    job = processor.get_job(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"job_id": job_id, **job})


@app.route("/queue")
def queue():
    items = processor.get_queue()
    return render_template("queue.html", items=items)


@app.route("/save", methods=["POST"])
def save():
    job_id = request.form.get("job_id", "")
    job = processor.get_job(job_id)
    if not job or job["status"] != "done":
        return redirect(url_for("queue"))
    result = job["result"]
    db.save_entry({
        "url":        result.get("url"),
        "title":      result.get("title"),
        "channel":    result.get("channel"),
        "duration":   result.get("duration"),
        "topic":      request.form.get("topic") or result.get("topic"),
        "subtopic":   request.form.get("subtopic") or result.get("subtopic"),
        "summary":    result.get("summary"),
        "key_points": result.get("key_points", []),
        "takeaways":  result.get("takeaways", []),
        "ai_opinion": result.get("ai_opinion"),
        "quotes":     result.get("quotes", []),
        "model_used": result.get("model_used"),
    })
    processor.remove_job(job_id)
    return redirect(url_for("queue"))


@app.route("/discard", methods=["POST"])
def discard():
    job_id = request.form.get("job_id", "")
    processor.remove_job(job_id)
    return redirect(url_for("queue"))


@app.route("/retry", methods=["POST"])
def retry():
    job_id = request.form.get("job_id", "")
    processor.requeue(job_id)
    return redirect(url_for("queue"))


@app.route("/library")
def library():
    topic_filter = request.args.get("topic")
    entries = db.get_all_entries()
    if topic_filter and topic_filter in TOPICS:
        entries = [e for e in entries if e["topic"] == topic_filter]
    grouped = {t: [e for e in entries if e["topic"] == t] for t in TOPICS}
    return render_template(
        "library.html",
        grouped=grouped,
        active_topic=topic_filter,
    )


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5003)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_app.py -v
```

Expected: 9 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add Flask routes with job management"
```

---

## Task 6: Base HTML Template

**Files:**
- Create: `templates/base.html`

- [ ] **Step 1: Create templates/base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YouTube Knowledge Library</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #0d1117;
      color: #c9d1d9;
      font-family: 'Courier New', Courier, monospace;
      font-size: 14px;
      min-height: 100vh;
    }

    /* Nav */
    nav {
      background: #161b22;
      border-bottom: 1px solid #30363d;
      padding: 12px 32px;
      display: flex;
      align-items: center;
      gap: 28px;
    }
    .nav-brand {
      color: #58a6ff;
      font-weight: bold;
      font-size: 15px;
      margin-right: 8px;
    }
    nav a {
      color: #8b949e;
      text-decoration: none;
      font-size: 13px;
      padding-bottom: 2px;
      position: relative;
    }
    nav a:hover { color: #c9d1d9; }
    nav a.active { color: #f0f6fc; border-bottom: 2px solid #58a6ff; }
    .badge {
      background: #da3633;
      color: #fff;
      border-radius: 10px;
      padding: 1px 6px;
      font-size: 11px;
      margin-left: 4px;
      vertical-align: middle;
    }

    /* Layout */
    main { max-width: 1100px; margin: 0 auto; padding: 36px 24px; }

    /* Typography */
    h1, h2 { color: #f0f6fc; margin-bottom: 20px; }
    h3 { color: #e6edf3; margin: 16px 0 8px; }
    h4 { color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin: 14px 0 6px; }
    p { line-height: 1.6; margin-bottom: 10px; }
    ul { padding-left: 20px; }
    li { line-height: 1.7; }

    /* Forms */
    textarea, input[type="text"] {
      background: #161b22;
      border: 1px solid #30363d;
      color: #c9d1d9;
      font-family: inherit;
      font-size: 13px;
      border-radius: 6px;
      padding: 10px 12px;
      width: 100%;
      resize: vertical;
    }
    textarea:focus, input[type="text"]:focus {
      outline: none;
      border-color: #58a6ff;
    }

    /* Buttons */
    .btn {
      display: inline-block;
      padding: 8px 16px;
      border: none;
      border-radius: 6px;
      font-family: inherit;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
    }
    .btn-primary { background: #238636; color: #fff; }
    .btn-primary:hover { background: #2ea043; }
    .btn-danger { background: #21262d; color: #da3633; border: 1px solid #da3633; }
    .btn-danger:hover { background: #da3633; color: #fff; }
    .btn-secondary { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
    .btn-secondary:hover { background: #30363d; color: #c9d1d9; }
    .btn-info { background: #1f6feb; color: #fff; }
    .btn-info:hover { background: #388bfd; }

    /* Tags / badges */
    .tag {
      display: inline-block;
      background: #1f3d2e;
      color: #3fb950;
      border-radius: 12px;
      padding: 2px 9px;
      font-size: 11px;
    }
    .badge-model {
      display: inline-block;
      background: #2d1f6e;
      color: #a5a5ff;
      border-radius: 12px;
      padding: 2px 9px;
      font-size: 11px;
      margin-left: 4px;
    }
    .badge-done { background: #1f3d2e; color: #3fb950; border-radius: 4px; padding: 2px 7px; font-size: 11px; }
    .badge-failed { background: #3d1f1f; color: #f85149; border-radius: 4px; padding: 2px 7px; font-size: 11px; }

    /* Divider */
    hr { border: none; border-top: 1px solid #21262d; margin: 20px 0; }

    /* Flash / error */
    .error-msg { color: #f85149; font-size: 13px; margin: 8px 0; }
  </style>
</head>
<body>
  <nav>
    <span class="nav-brand">YKL</span>
    <a href="/" {% if request.endpoint == 'index' %}class="active"{% endif %}>Process</a>
    <a href="/queue" {% if request.endpoint == 'queue' %}class="active"{% endif %}>
      Review Queue{% if queue_count %}<span class="badge">{{ queue_count }}</span>{% endif %}
    </a>
    <a href="/library" {% if request.endpoint == 'library' %}class="active"{% endif %}>Library</a>
  </nav>
  <main>
    {% block content %}{% endblock %}
  </main>
  <script src="/static/app.js"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Verify Flask can serve it**

```bash
python app.py &
curl -s http://localhost:5003/ | grep "YKL"
kill %1
```

Expected: HTML contains "YKL".

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add base HTML template with dark terminal theme"
```

---

## Task 7: Process Screen Template

**Files:**
- Create: `templates/process.html`

- [ ] **Step 1: Create templates/process.html**

```html
{% extends "base.html" %}
{% block content %}

{% if job_ids %}
<!-- Screen 2: Processing status -->
<h2>Processing</h2>
<p style="color:#8b949e; margin-bottom:24px;">Fetching transcripts and summarizing. This page polls automatically.</p>

<div id="job-list" style="display:flex; flex-direction:column; gap:10px;">
  {% for job_id in job_ids %}
  <div class="job-row" data-job-id="{{ job_id }}"
       style="background:#161b22; border:1px solid #30363d; border-radius:6px; padding:14px 18px; display:flex; justify-content:space-between; align-items:center;">
    <span class="job-url" style="color:#8b949e; font-size:12px; word-break:break-all;">{{ job_id }}</span>
    <span class="job-status" style="color:#f0f6fc; white-space:nowrap; margin-left:16px;">Pending...</span>
  </div>
  {% endfor %}
</div>

<div id="all-done" style="display:none; margin-top:24px; padding:16px; background:#1f3d2e; border-radius:6px; border:1px solid #238636;">
  All jobs processed.
  <a href="/queue" style="color:#3fb950; margin-left:8px;">View Review Queue →</a>
</div>

{% else %}
<!-- Screen 1: URL input form -->
<h2>Process YouTube Videos</h2>
<p style="color:#8b949e; margin-bottom:24px;">Paste one or more YouTube URLs below, one per line.</p>

<form method="POST" action="/process" style="display:flex; flex-direction:column; gap:16px; max-width:680px;">
  <textarea
    name="urls"
    rows="6"
    placeholder="https://www.youtube.com/watch?v=...&#10;https://youtu.be/..."
  ></textarea>

  <div style="display:flex; gap:24px; align-items:center;">
    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
      <input type="radio" name="mode" value="fast" checked
             style="accent-color:#58a6ff;">
      <span><strong style="color:#f0f6fc;">Fast</strong>
        <span style="color:#8b949e; font-size:12px;"> — Claude Haiku / qwen3.5 (~30s)</span>
      </span>
    </label>
    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
      <input type="radio" name="mode" value="quality"
             style="accent-color:#58a6ff;">
      <span><strong style="color:#f0f6fc;">Quality</strong>
        <span style="color:#8b949e; font-size:12px;"> — hermes3:70b (overnight batch)</span>
      </span>
    </label>
  </div>

  <div>
    <button type="submit" class="btn btn-primary">Process</button>
  </div>
</form>
{% endif %}

{% endblock %}

{% block scripts %}
{% if job_ids %}
<script>
  startPolling({{ job_ids | tojson }});
</script>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Verify renders in browser**

```bash
python app.py
```

Open `http://localhost:5003/`. Verify:
- URL textarea visible
- Fast/Quality radio buttons visible
- No JS errors in browser console

Stop server with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add templates/process.html
git commit -m "feat: add process screen with URL input and status view"
```

---

## Task 8: Review Queue Template

**Files:**
- Create: `templates/queue.html`

- [ ] **Step 1: Create templates/queue.html**

```html
{% extends "base.html" %}
{% block content %}

<h2>Review Queue</h2>

{% if not items %}
<p style="color:#8b949e; margin-top:16px;">Queue is empty. <a href="/" style="color:#58a6ff;">Process some videos →</a></p>

{% else %}
<p style="color:#8b949e; margin-bottom:24px;">
  {{ items|length }} item{{ 's' if items|length != 1 }}. Review each entry then save or discard.
</p>

<div style="display:flex; flex-direction:column; gap:12px;">
{% for item in items %}
<div style="background:#161b22; border:1px solid #30363d; border-radius:8px; overflow:hidden;">

  <!-- Header row -->
  <div onclick="toggleExpand('q-{{ item.job_id }}')"
       style="padding:14px 18px; display:flex; justify-content:space-between; align-items:center; cursor:pointer;">
    <div>
      <strong style="color:#f0f6fc;">
        {{ item.result.title if item.result and item.result.title else item.url }}
      </strong>
      {% if item.result and item.result.channel %}
      <span style="color:#8b949e; font-size:12px; margin-left:10px;">{{ item.result.channel }}</span>
      {% endif %}
    </div>
    <div style="display:flex; align-items:center; gap:8px; flex-shrink:0; margin-left:16px;">
      {% if item.result and item.result.model_used %}
      <span class="badge-model">{{ item.result.model_used }}</span>
      {% endif %}
      {% if item.status == 'done' %}
      <span class="badge-done">Done</span>
      {% else %}
      <span class="badge-failed">Failed</span>
      {% endif %}
      <span style="color:#8b949e; font-size:18px;">▾</span>
    </div>
  </div>

  <!-- Expandable body -->
  <div id="q-{{ item.job_id }}" style="display:none; padding:0 18px 18px; border-top:1px solid #21262d;">
    {% if item.status == 'done' and item.result %}

    <!-- Summary sections -->
    <div style="margin-top:16px;">
      <h4>Summary</h4>
      <p>{{ item.result.summary }}</p>

      <h4>Key Points</h4>
      <ul>{% for pt in item.result.key_points %}<li>{{ pt }}</li>{% endfor %}</ul>

      <h4>Takeaways</h4>
      <ul>{% for t in item.result.takeaways %}<li>{{ t }}</li>{% endfor %}</ul>

      <h4>AI Opinion</h4>
      <p>{{ item.result.ai_opinion }}</p>

      <h4>Notable Quotes</h4>
      <ul>{% for q in item.result.quotes %}<li>"{{ q }}"</li>{% endfor %}</ul>

      {% if item.result.duration %}
      <p style="color:#8b949e; font-size:12px; margin-top:10px;">Duration: {{ item.result.duration }}</p>
      {% endif %}
    </div>

    <hr>

    <!-- Save form -->
    <form method="POST" action="/save" style="margin-top:16px;">
      <input type="hidden" name="job_id" value="{{ item.job_id }}">

      <div style="margin-bottom:12px;">
        <span style="color:#8b949e; font-size:12px; display:block; margin-bottom:8px;">TOPIC</span>
        <div style="display:flex; gap:20px; flex-wrap:wrap;">
          {% for t in topics %}
          <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
            <input type="radio" name="topic" value="{{ t }}"
                   {% if item.result.topic == t %}checked{% endif %}
                   style="accent-color:#58a6ff;">
            <span style="color:#c9d1d9;">{{ t }}</span>
          </label>
          {% endfor %}
        </div>
      </div>

      <div style="margin-bottom:16px; max-width:360px;">
        <label style="color:#8b949e; font-size:12px; display:block; margin-bottom:6px;">SUBTOPIC</label>
        <input type="text" name="subtopic"
               value="{{ item.result.subtopic or '' }}"
               placeholder="e.g. Malware Analysis">
      </div>

      <div style="display:flex; gap:10px;">
        <button type="submit" class="btn btn-primary">Save to Library</button>
      </div>
    </form>

    <!-- Discard form -->
    <form method="POST" action="/discard" style="margin-top:8px; display:inline;">
      <input type="hidden" name="job_id" value="{{ item.job_id }}">
      <button type="submit" class="btn btn-danger">Discard</button>
    </form>

    {% else %}
    <!-- Failed state -->
    <div style="margin-top:16px;">
      <p class="error-msg">{{ item.error }}</p>
      <form method="POST" action="/retry">
        <input type="hidden" name="job_id" value="{{ item.job_id }}">
        <button type="submit" class="btn btn-info">Retry</button>
      </form>
    </div>
    {% endif %}

  </div>
</div>
{% endfor %}
</div>
{% endif %}

{% endblock %}
```

- [ ] **Step 2: Verify renders**

```bash
python app.py
```

Open `http://localhost:5003/queue`. Verify empty state message shows. Stop server.

- [ ] **Step 3: Commit**

```bash
git add templates/queue.html
git commit -m "feat: add review queue template with expand/save/discard"
```

---

## Task 9: Library Template

**Files:**
- Create: `templates/library.html`

- [ ] **Step 1: Create templates/library.html**

```html
{% extends "base.html" %}
{% block content %}

<h2>Library</h2>

<!-- Filter bar -->
<div style="display:flex; gap:10px; margin-bottom:28px; flex-wrap:wrap;">
  <a href="/library"
     class="btn {% if not active_topic %}btn-primary{% else %}btn-secondary{% endif %}">
    All
  </a>
  {% for t in topics %}
  <a href="/library?topic={{ t }}"
     class="btn {% if active_topic == t %}btn-primary{% else %}btn-secondary{% endif %}">
    {{ t }}
  </a>
  {% endfor %}
</div>

{% set total = grouped.values() | sum(attribute='__len__', start=0) %}
{% if total == 0 %}
<p style="color:#8b949e;">No entries saved yet. <a href="/" style="color:#58a6ff;">Process some videos →</a></p>

{% else %}
{% for topic in topics %}
{% if grouped[topic] %}

<h3 style="margin-bottom:14px; padding-bottom:8px; border-bottom:1px solid #21262d;">{{ topic }}</h3>

<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:16px; margin-bottom:32px;">
  {% for entry in grouped[topic] %}
  <div class="lib-card" onclick="toggleExpand('lib-{{ entry.id }}')"
       style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; cursor:pointer; transition:border-color 0.15s;">

    <!-- Card header -->
    <div style="margin-bottom:10px;">
      <strong style="color:#f0f6fc; display:block; margin-bottom:4px; line-height:1.4;">
        {{ entry.title or entry.url }}
      </strong>
      <span style="color:#8b949e; font-size:12px;">{{ entry.channel or 'Unknown' }}</span>
    </div>

    <!-- Meta row -->
    <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:10px;">
      {% if entry.subtopic %}
      <span class="tag">{{ entry.subtopic }}</span>
      {% endif %}
      {% if entry.model_used %}
      <span class="badge-model">{{ entry.model_used }}</span>
      {% endif %}
      {% if entry.duration %}
      <span style="color:#8b949e; font-size:11px;">{{ entry.duration }}</span>
      {% endif %}
      <span style="color:#8b949e; font-size:11px; margin-left:auto;">{{ entry.created_at[:10] }}</span>
    </div>

    <!-- Snippet -->
    <p style="color:#8b949e; font-size:12px; line-height:1.5; margin:0;">
      {{ (entry.summary or '')[:180] }}{% if entry.summary and entry.summary|length > 180 %}...{% endif %}
    </p>

    <!-- Expanded full entry -->
    <div id="lib-{{ entry.id }}" onclick="event.stopPropagation()"
         style="display:none; margin-top:16px; padding-top:16px; border-top:1px solid #21262d;">

      <h4>Summary</h4>
      <p style="color:#c9d1d9;">{{ entry.summary }}</p>

      <h4>Key Points</h4>
      <ul>{% for pt in entry.key_points %}<li>{{ pt }}</li>{% endfor %}</ul>

      <h4>Takeaways</h4>
      <ul>{% for t in entry.takeaways %}<li>{{ t }}</li>{% endfor %}</ul>

      <h4>AI Opinion</h4>
      <p style="color:#c9d1d9;">{{ entry.ai_opinion }}</p>

      {% if entry.quotes %}
      <h4>Notable Quotes</h4>
      <ul>{% for q in entry.quotes %}<li>"{{ q }}"</li>{% endfor %}</ul>
      {% endif %}

      <p style="margin-top:12px;">
        <a href="{{ entry.url }}" target="_blank" style="color:#58a6ff; font-size:12px;">
          Watch on YouTube ↗
        </a>
      </p>
    </div>
  </div>
  {% endfor %}
</div>

{% endif %}
{% endfor %}
{% endif %}

{% endblock %}
```

- [ ] **Step 2: Verify renders**

```bash
python app.py
```

Open `http://localhost:5003/library`. Verify empty state message shows. Stop server.

- [ ] **Step 3: Commit**

```bash
git add templates/library.html
git commit -m "feat: add library card grid template with topic grouping"
```

---

## Task 10: JavaScript

**Files:**
- Create: `static/app.js`

- [ ] **Step 1: Create static/app.js**

```javascript
/**
 * Toggle expand/collapse for queue items and library cards.
 * Pass the exact element ID to show/hide.
 */
function toggleExpand(id) {
  const el = document.getElementById(id);
  if (el) {
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
  }
}

const STATUS_LABELS = {
  pending:              'Pending...',
  fetching_transcript:  'Fetching transcript...',
  fetching_metadata:    'Fetching metadata...',
  summarizing:          'Summarizing...',
  done:                 'Done ✓',
  failed:               'Failed ✗',
  not_found:            'Not found',
};

/**
 * Poll /status/<job_id> every 2s for each job ID.
 * Updates DOM rows with current status. When all jobs reach a
 * terminal state (done/failed), shows the all-done banner.
 */
function startPolling(jobIds) {
  if (!jobIds || jobIds.length === 0) return;

  const terminal = new Set(['done', 'failed', 'not_found']);
  const settled = {};

  const interval = setInterval(async () => {
    for (const jobId of jobIds) {
      if (settled[jobId]) continue;

      try {
        const resp = await fetch('/status/' + jobId);
        const data = await resp.json();

        const row = document.querySelector('[data-job-id="' + jobId + '"]');
        if (row) {
          const urlEl = row.querySelector('.job-url');
          const statusEl = row.querySelector('.job-status');
          if (urlEl && data.url) urlEl.textContent = data.url;
          if (statusEl) {
            statusEl.textContent = STATUS_LABELS[data.status] || data.status;
            statusEl.style.color = data.status === 'done'   ? '#3fb950'
                                 : data.status === 'failed' ? '#f85149'
                                 : '#f0f6fc';
          }
        }

        if (terminal.has(data.status)) {
          settled[jobId] = true;
        }
      } catch (_) {
        // network error — keep polling
      }
    }

    const allSettled = jobIds.every(id => settled[id]);
    if (allSettled) {
      clearInterval(interval);
      const banner = document.getElementById('all-done');
      if (banner) banner.style.display = 'block';
    }
  }, 2000);
}
```

- [ ] **Step 2: Verify polling works end-to-end**

```bash
python app.py
```

Open `http://localhost:5003/`. Submit one real YouTube URL in Fast mode. Verify:
- Status row appears with spinner-like text updates
- After processing completes, "All jobs processed" banner appears
- `http://localhost:5003/queue` shows the entry

Stop server with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: add JS polling and expand/collapse interactions"
```

---

## Task 11: Smoke Test + Final Wiring

**Files:**
- Modify: `app.py` (add missing `db.init_db()` guard)

- [ ] **Step 1: Run full test suite — all must pass**

```bash
pytest -v
```

Expected: all tests PASS. If any fail, fix before continuing.

- [ ] **Step 2: Create .env from example**

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY if using Fast mode
```

- [ ] **Step 3: Start app and run full user journey**

```bash
python app.py
```

1. Open `http://localhost:5003/`
2. Paste one YouTube URL (short video recommended for speed)
3. Select Fast mode
4. Click Process — verify status row updates live
5. After done, click "View Review Queue"
6. Expand the entry — verify all 6 sections populated
7. Adjust topic radio if needed, edit subtopic if needed
8. Click "Save to Library"
9. Navigate to Library — verify card appears in correct topic group
10. Click card — verify full entry expands

- [ ] **Step 4: Test batch submit**

1. Paste 3 URLs in the textarea (one per line)
2. Click Process — verify 3 status rows appear and update independently

- [ ] **Step 5: Test error handling**

Submit a private YouTube URL (no transcript). Verify:
- Job appears in Review Queue with "Failed" badge
- Error message says "No transcript available for this video."
- "Retry" button visible

- [ ] **Step 6: Test Discard**

Submit a URL, let it process, then Discard from queue. Verify:
- Entry removed from queue
- Does NOT appear in Library

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "feat: YouTube Knowledge Library MVP complete"
```

---

## Post-MVP Backlog (do not implement now)

- Search within library
- Export entries to markdown/PDF
- Feed saved knowledge into Hermes stack
- YouTube playlist bulk import
- Edit saved entries
