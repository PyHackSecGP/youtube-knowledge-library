#!/usr/bin/env python3
"""
Upload books from category subfolders to matching Open WebUI knowledge collections.
Run on base after rsync from Mac.

Usage:
    python3 upload_books_by_category.py [~/Books/AI-Library]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OWUI_URL = os.getenv("OPENWEBUI_URL", "http://100.126.22.55:3001")
OWUI_KEY = os.getenv("OPENWEBUI_API_KEY", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {OWUI_KEY}"}


def get_or_create_collection(name: str) -> str | None:
    try:
        r = requests.get(f"{OWUI_URL}/api/v1/knowledge/", headers=_headers(), timeout=10)
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        for col in items:
            if col.get("name") == name:
                return col["id"]
        # Not found — create it
        r = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/create",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"name": name, "description": f"Books — {name}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()["id"]
        print(f"    [collection create failed] {r.status_code}: {r.text[:100]}")
        return None
    except Exception as e:
        print(f"    [collection error] {e}")
        return None


MAX_TEXT_BYTES = 400_000  # ~400KB — keeps Open WebUI happy


def pdf_to_text(path: Path) -> str | None:
    try:
        import fitz
        doc = fitz.open(str(path))
        parts: list[str] = []
        total = 0
        for page in doc:
            t = page.get_text()
            if not t.strip():
                continue
            encoded = t.encode("utf-8", errors="ignore")
            if total + len(encoded) > MAX_TEXT_BYTES:
                # Add partial page to fill quota then stop
                remaining = MAX_TEXT_BYTES - total
                parts.append(encoded[:remaining].decode("utf-8", errors="ignore"))
                break
            parts.append(t)
            total += len(encoded)
        doc.close()
        return "\n\n".join(parts) or None
    except Exception:
        return None


def _wait_for_file(file_id: str, timeout: int = 60) -> bool:
    """Poll until file status is completed or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{OWUI_URL}/api/v1/files/{file_id}",
                             headers=_headers(), timeout=10)
            status = (r.json().get("data") or {}).get("status")
            if status == "completed":
                return True
            if status == "error":
                return False
        except Exception:
            pass
        time.sleep(2)
    return True  # proceed anyway after timeout


def upload_file(path: Path, collection_id: str) -> str:
    text = pdf_to_text(path)
    if text:
        fname = path.stem[:80] + ".txt"
        data  = text.encode("utf-8", errors="ignore")
        ctype = "text/plain"
    else:
        fname = path.name
        try:
            data = path.read_bytes()
        except Exception as e:
            return f"read error: {e}"
        ctype = "application/pdf"

    try:
        r = requests.post(f"{OWUI_URL}/api/v1/files/", headers=_headers(),
                          files={"file": (fname, data, ctype)}, timeout=90)
        if r.status_code != 200:
            return f"upload {r.status_code}: {r.text[:80]}"
        file_id = r.json().get("id")
        if not file_id:
            return "no file_id"

        _wait_for_file(file_id)

        add = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/{collection_id}/file/add",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"file_id": file_id}, timeout=30,
        )
        if add.status_code == 400 and "Duplicate" in add.text:
            return "duplicate"
        if add.status_code != 200:
            return f"add {add.status_code}: {add.text[:80]}"
        return "ok"
    except Exception as e:
        return f"error: {e}"


def main() -> None:
    if not OWUI_KEY:
        print("OPENWEBUI_API_KEY not set.")
        sys.exit(1)

    base_folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Books" / "AI-Library"

    # Find all category subfolders
    subdirs = [d for d in base_folder.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not subdirs:
        print(f"No subfolders found in {base_folder}")
        print("Run sort_books.py on Mac first, then rsync here.")
        sys.exit(1)

    print(f"Found {len(subdirs)} category folders in {base_folder}\n")
    total_ok = total_fail = 0

    for subdir in sorted(subdirs):
        category = subdir.name
        collection_name = category.replace("_", "-") + "-books"
        pdfs = sorted(subdir.glob("*.pdf"))
        if not pdfs:
            continue

        col_id = get_or_create_collection(collection_name)
        if not col_id:
            print(f"[{category}] Could not create collection — skipping")
            continue

        print(f"\n[{category}] → collection: {collection_name}  ({len(pdfs)} books)")
        ok = fail = 0
        for i, pdf in enumerate(pdfs, 1):
            print(f"  [{i}/{len(pdfs)}] {pdf.name[:60]}", end=" ... ", flush=True)
            result = upload_file(pdf, col_id)
            print(result)
            if result in ("ok", "duplicate"):
                ok += 1
            else:
                fail += 1
        print(f"  → {ok} ok, {fail} failed")
        total_ok += ok
        total_fail += fail

    print(f"\n{'='*50}")
    print(f"DONE — {total_ok} uploaded, {total_fail} failed")
    print(f"Open WebUI: {OWUI_URL}")


if __name__ == "__main__":
    main()
