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
    """Inject queue_count and topics into all template contexts."""
    return {
        "queue_count": processor.get_queue_count(),
        "topics": TOPICS,
    }


@app.route("/")
def index():
    """Render the URL submission page."""
    return render_template("process.html")


@app.route("/process", methods=["POST"])
def process():
    """Submit URLs for processing and show job IDs on success."""
    raw = request.form.get("urls", "")
    urls = [u.strip() for u in raw.splitlines() if u.strip()]
    mode = request.form.get("mode", "fast")
    if not urls:
        return redirect(url_for("index"))
    job_ids = processor.submit(urls, mode)
    return render_template("process.html", job_ids=job_ids)


@app.route("/status/<job_id>")
def status(job_id: str):
    """Return JSON status for a given job ID."""
    job = processor.get_job(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"job_id": job_id, **job})


@app.route("/queue")
def queue():
    """Render the review queue showing done/failed jobs."""
    items = processor.get_queue()
    return render_template("queue.html", items=items)


@app.route("/save", methods=["POST"])
def save():
    """Save a completed job to the library and remove it from the queue."""
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
    """Remove a job from the queue without saving."""
    job_id = request.form.get("job_id", "")
    processor.remove_job(job_id)
    return redirect(url_for("queue"))


@app.route("/retry", methods=["POST"])
def retry():
    """Requeue a failed job for reprocessing."""
    job_id = request.form.get("job_id", "")
    processor.requeue(job_id)
    return redirect(url_for("queue"))


@app.route("/library")
def library():
    """Render the library, optionally filtered by topic."""
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
