# YouTube Knowledge Library — Design Spec
**Date:** 2026-06-24  
**Status:** Approved

---

## Overview

A Flask web app that converts YouTube videos into structured, searchable knowledge entries. Paste one or more URLs, get AI-generated summaries with key points and takeaways, review them, and save to a topic-organized library.

---

## Architecture

Single Flask app. SQLite persistence. Background thread processing with JS polling for async UX.

### Routes

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | Home — URL input form (Process screen) |
| POST | `/process` | Submit URLs, start background jobs, return job IDs |
| GET | `/status/<job_id>` | Poll job status and result (JS polls every 2s) |
| POST | `/save` | Persist reviewed entry to SQLite |
| GET | `/library` | Card grid of all saved entries |
| GET | `/queue` | Review Queue — processed but unreviewed entries |

### Navigation

Three-item nav bar present on all pages:
- **Process** — submit new URLs
- **Review Queue** `[badge count]` — entries awaiting review
- **Library** — all saved entries

---

## Processing Pipeline

For each submitted URL, a background thread executes:

1. **Transcript fetch** — `youtube-transcript-api` pulls transcript text
2. **Metadata fetch** — `noembed.com` oEmbed API returns title and channel (no API key required). Duration estimated from transcript word count (words ÷ 130 wpm).
3. **LLM summarization** — structured JSON prompt sent to primary model
4. **Result stored** — in-memory job dict, keyed by `job_id`, status transitions: `pending → processing → done | failed`

### Model Selection

User picks mode at submission time:

| Mode | Primary | Timeout | Fallback chain |
|------|---------|---------|----------------|
| Fast (daytime) | Claude Haiku API | 60s | qwen3.5:latest → llama3.2:3b |
| Quality (overnight) | hermes3:70b (Ollama) | 30min | qwen3.5:latest → llama3.2:3b |

- Claude Haiku endpoint: Anthropic API (key via env var `ANTHROPIC_API_KEY`)
- Ollama endpoint: `http://100.126.22.55:11434`
- Model name recorded in DB and shown as badge on every card

If `ANTHROPIC_API_KEY` is not set, Fast mode skips Claude and starts at `qwen3.5:latest`.

### LLM Prompt

Single prompt returning structured JSON (Ollama `format: "json"`, Claude tool use / JSON mode):

```
You are a knowledge extraction assistant. Given this YouTube transcript, return a JSON object with exactly these keys:

- "summary": string, 2-3 paragraphs
- "key_points": array of strings
- "takeaways": array of actionable strings
- "ai_opinion": string, your commentary and analysis
- "quotes": array of notable direct quote strings from the transcript
- "topic": one of ["Cybersecurity", "Investing", "World Events", "Personal Development"]
- "subtopic": string, specific sub-category (e.g. "Malware Analysis", "Index Funds", "Geopolitics")

Transcript: {transcript}
```

---

## Data Model

SQLite, single table:

```sql
CREATE TABLE entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT NOT NULL,
    title       TEXT,
    channel     TEXT,
    duration    TEXT,
    topic       TEXT NOT NULL,
    subtopic    TEXT,
    summary     TEXT,
    key_points  TEXT,   -- JSON array
    takeaways   TEXT,   -- JSON array
    ai_opinion  TEXT,
    quotes      TEXT,   -- JSON array
    model_used  TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Topics constrained to: `Cybersecurity`, `Investing`, `World Events`, `Personal Development`.

---

## UI Screens

### Screen 1 — Process (Home `/`)
- Textarea: one or more YouTube URLs, one per line
- Model mode toggle: **Fast** (Claude Haiku) / **Quality** (Ollama 70b)
- Submit button: "Process"
- After submit: transitions to processing status view

### Screen 2 — Processing Status
- Per-job progress rows: URL + spinner/status text
- Status messages cycle: "Fetching transcript…" → "Summarizing…" → "Done" / "Failed"
- JS polls `/status/<job_id>` every 2s
- On all jobs done: nav badge updates, prompt to visit Review Queue

### Screen 3 — Review Queue (`/queue`)
- List of processed-but-unsaved entries
- Each entry shows: title, channel, model badge, status badge (Done / Failed)
- Click entry → expand inline to full review view:
  - All 6 summary sections displayed
  - Topic: 4 radio buttons (AI pre-selects one)
  - Subtopic: text field pre-filled by AI, editable
  - "Save" and "Discard" buttons (Discard permanently removes entry from queue — not saved to library)
- Failed entries show error type + "Retry" button

### Screen 4 — Library (`/library`)
- Card grid grouped by topic heading
- Each card: title, channel, subtopic tag, model badge, date, 2-line summary snippet
- Click card → expands to full entry inline (all 6 sections)
- Filter bar at top: show all topics or filter to one

---

## Error Handling

### Per-job retry logic
- **Transcript unavailable** (private video, no captions): immediate fail, no retry. Error: "No transcript available for this video."
- **Ollama unreachable**: retry 3× with 10s backoff. If all fail: "Ollama unreachable — check claw-core."
- **Claude API error**: retry 3× with 5s backoff. If all fail: fall back to Ollama cascade.
- **Model timeout**: cascade to next smaller model. Record actual model used.
- **JSON parse failure** (malformed LLM output): retry once with stricter prompt. If fails: "Summarization failed — try a different model."

### Error states surfaced to user
Every job ends in one of: `done`, `failed`, or `retrying`. No silent failures.  
Failed jobs persist in Review Queue with:
- Red "Failed" badge
- Human-readable error message
- "Retry" button (re-queues the job)

---

## File Structure

```
youtube-knowledge-library/
├── app.py              # Flask app, routes, job store
├── processor.py        # Background pipeline: transcript → metadata → LLM
├── llm.py              # LLM abstraction: Claude API + Ollama cascade
├── db.py               # SQLite schema init + CRUD
├── templates/
│   ├── base.html       # Nav bar, dark terminal theme
│   ├── process.html    # Screen 1 + 2
│   ├── queue.html      # Screen 3
│   └── library.html    # Screen 4
├── static/
│   └── app.js          # JS polling, expand/collapse, badge updates
├── requirements.txt
├── .env.example        # ANTHROPIC_API_KEY=
└── README.md
```

---

## Dependencies

```
flask>=3.0
youtube-transcript-api>=0.6
anthropic>=0.25
requests>=2.31
python-dotenv>=1.0
```

Ollama accessed via HTTP (no Python client needed — direct REST calls to `http://100.126.22.55:11434`).

---

## Out of Scope (MVP)

- Search within library
- Export to markdown/PDF
- Feed saved knowledge into Hermes stack
- User accounts / multi-user
- YouTube playlist bulk import
