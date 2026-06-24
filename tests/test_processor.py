import pytest
from unittest.mock import patch
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
