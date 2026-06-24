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
