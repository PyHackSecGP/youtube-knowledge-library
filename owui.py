"""Push saved entries into per-persona Open WebUI Knowledge collections for RAG."""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Topic → (persona_name, collection_description)
PERSONA_MAP: dict[str, tuple[str, str]] = {
    "Cybersecurity": (
        "Sentinel",
        "GP's curated cybersecurity videos: hacking, CTF, malware, penetration testing, threat intel",
    ),
    "Investing": (
        "Vault",
        "GP's curated investing and finance videos: stocks, markets, wealth building, personal finance",
    ),
    "World Events": (
        "Atlas",
        "GP's curated world events and geopolitics videos: news, international relations, policy",
    ),
    "Personal Development": (
        "Forge",
        "GP's curated personal development videos: fitness, habits, productivity, mindset",
    ),
}
_FALLBACK: tuple[str, str] = ("Council", "GP's general knowledge video library")

PERSONA_COLORS: dict[str, str] = {
    "Sentinel": "#ef4444",
    "Vault":    "#22c55e",
    "Atlas":    "#3b82f6",
    "Forge":    "#f59e0b",
    "Council":  "#6b7280",
}


def get_persona_for_topic(topic: str) -> str:
    """Return persona name for a given topic string."""
    return PERSONA_MAP.get(topic, _FALLBACK)[0]


def _url() -> str:
    return os.getenv("OPENWEBUI_URL", "http://100.126.22.55:3001")


def _key() -> str:
    return os.getenv("OPENWEBUI_API_KEY", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_key()}"}


def _collection_name_for(topic: str) -> tuple[str, str]:
    persona, desc = PERSONA_MAP.get(topic, _FALLBACK)
    return f"{persona} — Knowledge Base", desc


def _get_or_create_collection(name: str, description: str) -> str | None:
    """Return collection ID for name, creating it if absent."""
    try:
        resp = requests.get(f"{_url()}/api/v1/knowledge/", headers=_headers(), timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        for col in items:
            if col.get("name") == name:
                return col["id"]
        resp = requests.post(
            f"{_url()}/api/v1/knowledge/create",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"name": name, "description": description},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["id"]
        return None
    except Exception:
        return None


def setup_all_collections() -> dict[str, str | None]:
    """Create all persona collections. Returns {persona_name: collection_id}."""
    results: dict[str, str | None] = {}
    for _topic, (persona, desc) in PERSONA_MAP.items():
        col_id = _get_or_create_collection(f"{persona} — Knowledge Base", desc)
        results[persona] = col_id
    return results


def _format_entry(entry: dict) -> str:
    lines = [
        f"# {entry.get('title', 'Untitled')}",
        f"Channel: {entry.get('channel', 'Unknown')}",
        f"Persona: {entry.get('persona', get_persona_for_topic(entry.get('topic', '')))}",
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
    if isinstance(sa, str):
        import json
        try:
            sa = json.loads(sa)
        except Exception:
            sa = {}
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
    """Upload entry to its persona's Knowledge collection. Returns True on success."""
    if not _key():
        return False

    topic = entry.get("topic", "")
    col_name, col_desc = _collection_name_for(topic)
    collection_id = _get_or_create_collection(col_name, col_desc)
    if not collection_id:
        return False

    content = _format_entry(entry)
    title = entry.get("title") or "untitled"
    filename = f"{title[:60].replace('/', '-')}.txt"

    try:
        upload = requests.post(
            f"{_url()}/api/v1/files/",
            headers=_headers(),
            files={"file": (filename, content.encode("utf-8"), "text/plain")},
            timeout=30,
        )
        if upload.status_code != 200:
            return False
        file_id = upload.json().get("id")
        if not file_id:
            return False

        add = requests.post(
            f"{_url()}/api/v1/knowledge/{collection_id}/file/add",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"file_id": file_id},
            timeout=30,
        )
        if add.status_code == 400 and "Duplicate" in add.text:
            return True
        return add.status_code == 200

    except Exception:
        return False
