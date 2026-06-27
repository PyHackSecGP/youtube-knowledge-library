import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

import db
import owui
import processor

load_dotenv()

app = Flask(__name__)

TOPICS = ["Cybersecurity", "Investing", "World Events", "Personal Development"]


@app.context_processor
def inject_globals() -> dict:
    return {
        "queue_count": processor.get_queue_count(),
        "topics": TOPICS,
        "owui_enabled": bool(os.getenv("OPENWEBUI_API_KEY")),
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

    topic = request.form.get("topic") or result.get("topic") or "Cybersecurity"
    if topic not in TOPICS:
        topic = "Cybersecurity"
    subtopic = request.form.get("subtopic") or result.get("subtopic") or ""

    entry = {
        "url":            result.get("url"),
        "title":          result.get("title"),
        "channel":        result.get("channel"),
        "duration":       result.get("duration"),
        "topic":          topic,
        "subtopic":       subtopic,
        "summary":        result.get("summary"),
        "key_points":     result.get("key_points", []),
        "takeaways":      result.get("takeaways", []),
        "ai_opinion":     result.get("ai_opinion"),
        "quotes":         result.get("quotes", []),
        "model_used":     result.get("model_used"),
        "input_tokens":   result.get("input_tokens", 0),
        "output_tokens":  result.get("output_tokens", 0),
        "cost_usd":       result.get("cost_usd", 0.0),
        "stock_analysis": result.get("stock_analysis"),
    }
    entry_id = db.save_entry(entry)
    processor.remove_job(job_id)

    # Auto-sync to Open WebUI if API key is configured
    if os.getenv("OPENWEBUI_API_KEY"):
        saved = db.get_entry(entry_id)
        if saved and owui.sync_entry(saved):
            db.mark_synced(entry_id)

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
    return render_template("library.html", grouped=grouped, active_topic=topic_filter)


@app.route("/entry/<int:entry_id>")
def entry(entry_id: int):
    """Full-screen detail view for a single library entry."""
    e = db.get_entry(entry_id)
    if not e:
        return redirect(url_for("library"))
    return render_template("entry.html", entry=e)


@app.route("/sync/<int:entry_id>", methods=["POST"])
def sync(entry_id: int):
    """Manually sync one entry to Open WebUI."""
    entry = db.get_entry(entry_id)
    if not entry:
        return jsonify({"ok": False, "error": "not found"}), 404
    if not os.getenv("OPENWEBUI_API_KEY"):
        return jsonify({"ok": False, "error": "OPENWEBUI_API_KEY not set in .env"}), 400
    ok = owui.sync_entry(entry)
    if ok:
        db.mark_synced(entry_id)
    return jsonify({"ok": ok})


@app.route("/sync-all", methods=["POST"])
def sync_all():
    """Sync all unsynced entries to Open WebUI. Returns per-entry results."""
    if not os.getenv("OPENWEBUI_API_KEY"):
        return jsonify({"ok": False, "error": "OPENWEBUI_API_KEY not set in .env"}), 400
    entries = db.get_all_entries()
    unsynced = [e for e in entries if not e.get("synced_owui")]
    results = []
    for e in unsynced:
        ok = owui.sync_entry(e)
        if ok:
            db.mark_synced(e["id"])
        results.append({"id": e["id"], "title": e["title"], "ok": ok})
    return jsonify({"ok": True, "results": results, "total": len(unsynced)})


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", debug=True, port=5003)
