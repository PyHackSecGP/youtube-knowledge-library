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
