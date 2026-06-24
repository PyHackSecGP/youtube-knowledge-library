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
    if mode not in ("fast", "quality"):
        raise ValueError(f"mode must be 'fast' or 'quality', got {mode!r}")

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
    try:
        return json.loads(msg.content[0].text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude returned invalid JSON: {exc}") from exc


def _ollama(prompt: str, model: str, timeout: int) -> dict:
    """Call Ollama with JSON format enforced."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": model, "prompt": prompt, "format": "json", "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    try:
        return json.loads(resp.json()["response"])
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc
