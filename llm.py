import json
import os

import requests
from anthropic import Anthropic

OLLAMA_URL = "http://100.126.22.55:11434"

PROMPT_TEMPLATE = """You are a knowledge extraction assistant. Given this YouTube transcript, return a JSON object with exactly these keys:

- "summary": string — comprehensive prose summary. Use markdown formatting: **bold** for key terms and important concepts, ## for major section headings, *italic* for emphasis, bullet lists where appropriate. Scale length to content richness: minimum 3-4 solid paragraphs for short/simple videos, up to 8-10 paragraphs for dense/complex videos. Cover all major points, arguments, examples, and conclusions.
- "key_points": array of strings — every significant point made, not just the top 3. Each point may use **bold** for the core claim.
- "takeaways": array of actionable strings — concrete things the viewer should do or remember
- "ai_opinion": string — your commentary and analysis in markdown. Include **what you agree with**, *what you're skeptical of*, and your overall assessment.
- "quotes": array of notable direct quote strings from the transcript
- "topic": one of ["Cybersecurity", "Investing", "World Events", "Personal Development"]
- "subtopic": string, specific sub-category (e.g. "Malware Analysis", "Index Funds", "Geopolitics")
- "stock_analysis": object with these keys:
  - "relevant": boolean — true only if this video meaningfully discusses stocks, companies, markets, investing, or specific financial instruments
  - "tickers": array of strings — stock tickers directly or strongly referenced (e.g. ["AAPL", "NVDA"]). Empty array if not relevant.
  - "thesis": string — the core investment thesis or financial insight. Empty string if not relevant.
  - "action": one of ["buy", "watch", "avoid", "neutral"] — suggested stance based on content. Use "neutral" if not relevant.
  - "catalysts": array of strings — key catalysts, events, or drivers mentioned. Empty if not relevant.
  - "risk_level": one of ["low", "medium", "high", "not applicable"]
  - "time_horizon": one of ["short-term", "medium-term", "long-term", "not applicable"]

Transcript: {transcript}"""

# (model, timeout_seconds)
_QUALITY_MODELS = [
    ("hermes3:70b",     600),
    ("qwen3.5:latest",  300),
    ("llama3.2:3b",     180),
]

_FAST_MODELS = [
    ("qwen3.5:latest",  300),
    ("llama3.2:3b",     180),
]

_MAX_WORDS = 12000
_MAX_WORDS_OLLAMA = 6000

# Claude Haiku 4.5 pricing (per million tokens)
_HAIKU_INPUT_COST  = 0.80
_HAIKU_OUTPUT_COST = 4.00


def _truncate(transcript: str, max_words: int = _MAX_WORDS) -> str:
    words = transcript.split()
    return " ".join(words[:max_words]) if len(words) > max_words else transcript


def _validate(result: dict) -> None:
    if not result.get("summary"):
        raise RuntimeError("LLM returned empty summary")


def summarize(transcript: str, mode: str) -> tuple[dict, str]:
    """Summarize transcript. Returns (result_dict, model_name_used).

    result_dict may include input_tokens, output_tokens, cost_usd when Claude is used.
    Raises RuntimeError if all models fail.
    """
    if mode not in ("fast", "quality"):
        raise ValueError(f"mode must be 'fast' or 'quality', got {mode!r}")

    api_key = os.getenv("ANTHROPIC_API_KEY")

    # Claude first for both modes — fast and accurate
    if api_key:
        claude_transcript = _truncate(transcript, _MAX_WORDS)
        prompt = PROMPT_TEMPLATE.format(transcript=claude_transcript)
        try:
            result, usage = _claude(prompt, api_key)
            _validate(result)
            result["input_tokens"] = usage["input_tokens"]
            result["output_tokens"] = usage["output_tokens"]
            result["cost_usd"] = usage["cost_usd"]
            return result, "claude-haiku-4-5"
        except Exception:
            pass

    # Ollama fallback — smaller context window for local models
    ollama_transcript = _truncate(transcript, _MAX_WORDS_OLLAMA)
    prompt = PROMPT_TEMPLATE.format(transcript=ollama_transcript)
    models = _QUALITY_MODELS if mode == "quality" else _FAST_MODELS

    for model, timeout in models:
        try:
            result, usage = _ollama(prompt, model, timeout)
            _validate(result)
            result["input_tokens"] = usage["input_tokens"]
            result["output_tokens"] = usage["output_tokens"]
            result["cost_usd"] = 0.0
            return result, model
        except Exception:
            continue

    raise RuntimeError("All models failed")


def _claude(prompt: str, api_key: str, timeout: int = 300) -> tuple[dict, dict]:
    """Call Claude Haiku and parse JSON response. Returns (result, usage_info)."""
    client = Anthropic(api_key=api_key, timeout=timeout)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system="Return only valid JSON, no markdown code fences, no explanation.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude returned invalid JSON: {exc}") from exc

    usage = {
        "input_tokens":  msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "cost_usd": round(
            msg.usage.input_tokens  * _HAIKU_INPUT_COST  / 1_000_000 +
            msg.usage.output_tokens * _HAIKU_OUTPUT_COST / 1_000_000,
            6
        ),
    }
    return result, usage


def _ollama(prompt: str, model: str, timeout: int) -> tuple[dict, dict]:
    """Call Ollama with JSON format enforced. Returns (result, usage_info)."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": model, "prompt": prompt, "format": "json", "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        result = json.loads(data["response"])
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc

    usage = {
        "input_tokens":  data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
    }
    return result, usage
