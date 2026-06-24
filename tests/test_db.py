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
