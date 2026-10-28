"""Export YKL entry → brain CouchDB vault as markdown.

Writes to `30-cybersecurity/youtube/<id>-<slug>.md` via vault-write.sh --force.
Falls back to error dict on vault failure.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

VAULT_WRITE = Path.home() / "projects/brain/scripts/vault-write.sh"
VAULT_FOLDER = "30-cybersecurity/youtube"


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return (s or "untitled")[:60]


def _render(entry: dict) -> str:
    key_points = entry.get("key_points") or []
    takeaways = entry.get("takeaways") or []
    quotes = entry.get("quotes") or []
    sa = entry.get("stock_analysis") or {}
    created = entry.get("created_at", "")[:10]

    md = [
        "---",
        "type: youtube-video",
        f"ykl_id: {entry.get('id')}",
        f"topic: {entry.get('topic') or ''}",
        f"subtopic: {entry.get('subtopic') or ''}",
        f"channel: {entry.get('channel') or ''}",
        f"persona: {entry.get('persona') or ''}",
        f"duration: {entry.get('duration') or ''}",
        f"created: {created}",
        f"source: {entry.get('url') or ''}",
        f"model: {entry.get('model_used') or ''}",
        f"cost_usd: {entry.get('cost_usd') or 0}",
        "tags: [youtube, ykl]",
        "---",
        "",
        f"# {entry.get('title') or 'Untitled'}",
        "",
        f"**Channel:** {entry.get('channel') or 'Unknown'} · "
        f"**Duration:** {entry.get('duration') or '?'} · "
        f"**Topic:** {entry.get('topic') or '?'}"
        + (f" / {entry['subtopic']}" if entry.get("subtopic") else ""),
        "",
        f"**Source:** {entry.get('url')}",
        "",
        "## Summary",
        "",
        entry.get("summary") or "_(no summary)_",
        "",
    ]
    if key_points:
        md += ["## Key points", ""]
        md += [f"- {p}" for p in key_points]
        md.append("")
    if takeaways:
        md += ["## Takeaways", ""]
        md += [f"- {t}" for t in takeaways]
        md.append("")
    if quotes:
        md += ["## Quotes", ""]
        md += [f"> {q}" for q in quotes]
        md.append("")
    if entry.get("ai_opinion"):
        md += ["## AI opinion", "", entry["ai_opinion"], ""]
    if sa and sa.get("relevant") and sa.get("tickers"):
        md += [
            "## Stock analysis",
            "",
            f"- Tickers: {', '.join(sa.get('tickers') or [])}",
            f"- Action: **{sa.get('action') or ''}**",
            f"- Thesis: {sa.get('thesis') or ''}",
            f"- Catalysts: {sa.get('catalysts') or ''}",
            f"- Risk: {sa.get('risk') or ''}",
            f"- Horizon: {sa.get('time_horizon') or ''}",
            "",
        ]
    md += [
        "---",
        f"_Exported from YKL on {datetime.now():%Y-%m-%d %H:%M} · id={entry.get('id')}_",
        "",
    ]
    return "\n".join(md)


def export_entry(entry: dict) -> dict:
    """Write entry markdown to brain vault. Returns {ok, path, error?}."""
    if not entry:
        return {"ok": False, "error": "no entry"}
    slug = _slug(entry.get("title") or "")
    path = f"{VAULT_FOLDER}/{entry.get('id')}-{slug}.md"
    content = _render(entry)
    try:
        r = subprocess.run(
            [str(VAULT_WRITE), "--force", path],
            input=content,
            text=True,
            capture_output=True,
            timeout=15,
        )
        if r.returncode == 0:
            try:
                resp = json.loads(r.stdout.strip() or "{}")
            except Exception:
                resp = {}
            return {"ok": True, "path": path, "resp": resp}
        return {"ok": False, "error": r.stderr.strip() or "vault-write failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
