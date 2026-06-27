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
    if mode not in ("fast", "quality"):
        raise ValueError(f"mode must be 'fast' or 'quality', got {mode!r}")
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
    with _lock:
        if job_id not in jobs:
            return
    _set(job_id, "status", "fetching_transcript")
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
