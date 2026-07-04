"""Push saved entries as files into an Open WebUI Knowledge collection for RAG."""
import os

import requests

OWUI_URL = os.getenv("OPENWEBUI_URL", "http://100.126.22.55:3001")
OWUI_KEY = os.getenv("OPENWEBUI_API_KEY", "")
COLLECTION_NAME = os.getenv("OPENWEBUI_COLLECTION", "YouTube Knowledge Library")


def _headers() -> dict:
    return {"Authorization": f"Bearer {OWUI_KEY}"}


def _get_or_create_collection() -> str | None:
    """Return the knowledge collection ID, creating it if it doesn't exist."""
    try:
        resp = requests.get(f"{OWUI_URL}/api/v1/knowledge/", headers=_headers(), timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        for col in items:
            if col.get("name") == COLLECTION_NAME:
                return col["id"]
        # Create it
        resp = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/create",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"name": COLLECTION_NAME, "description": "Auto-synced YouTube video summaries"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["id"]
        return None
    except Exception:
        return None


def _format_entry(entry: dict) -> str:
    lines = [
        f"# {entry.get('title', 'Untitled')}",
        f"Channel: {entry.get('channel', 'Unknown')}",
        f"Topic: {entry.get('topic', '')} / {entry.get('subtopic', '')}",
        f"Duration: {entry.get('duration', '')}",
        f"Source: {entry.get('url', '')}",
        "",
        "## Summary",
        entry.get("summary", ""),
        "",
        "## Key Points",
    ]
    for pt in entry.get("key_points", []):
        lines.append(f"- {pt}")
    lines += ["", "## Actionable Takeaways"]
    for t in entry.get("takeaways", []):
        lines.append(f"- {t}")
    lines += ["", "## AI Opinion", entry.get("ai_opinion", "")]

    sa = entry.get("stock_analysis") or {}
    if sa.get("relevant"):
        lines += ["", "## Stock Analysis"]
        if sa.get("tickers"):
            lines.append(f"Tickers: {', '.join(sa['tickers'])}")
        if sa.get("thesis"):
            lines.append(f"Thesis: {sa['thesis']}")
        lines.append(f"Action: {sa.get('action', 'neutral').upper()}")
        if sa.get("catalysts"):
            lines.append("Catalysts:")
            for c in sa["catalysts"]:
                lines.append(f"  - {c}")

    if entry.get("quotes"):
        lines += ["", "## Notable Quotes"]
        for q in entry["quotes"]:
            lines.append(f'"{q}"')

    return "\n".join(lines)


def sync_entry(entry: dict) -> bool:
    """Upload entry as a file into the Knowledge collection. Returns True on success."""
    if not OWUI_KEY:
        return False

    collection_id = _get_or_create_collection()
    if not collection_id:
        return False

    content = _format_entry(entry)
    title = entry.get("title") or "untitled"
    filename = f"{title[:60].replace('/', '-')}.txt"

    try:
        # Step 1: Upload file
        upload = requests.post(
            f"{OWUI_URL}/api/v1/files/",
            headers=_headers(),
            files={"file": (filename, content.encode("utf-8"), "text/plain")},
            timeout=30,
        )
        if upload.status_code != 200:
            return False
        file_id = upload.json().get("id")
        if not file_id:
            return False

        # Step 2: Add file to knowledge collection
        add = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/{collection_id}/file/add",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"file_id": file_id},
            timeout=30,
        )
        # 400 "Duplicate content" means it's already in the collection — treat as success
        if add.status_code == 400 and "Duplicate" in add.text:
            return True
        return add.status_code == 200

    except Exception:
        return False
