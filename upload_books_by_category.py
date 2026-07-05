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
        items = r.json().get("items", [])
        for col in items:
            if col["name"] == name:
                return col["id"]
        r = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/create",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"name": name, "description": f"Books — {name}"},
            timeout=10,
        )
        return r.json()["id"] if r.status_code == 200 else None
    except Exception:
        return None


def pdf_to_text(path: Path) -> str | None:
    try:
        import fitz
        doc = fitz.open(str(path))
        pages = [p.get_text() for p in doc if p.get_text().strip()]
        doc.close()
        return "\n\n".join(pages) or None
    except Exception:
        return None


def upload_file(path: Path, collection_id: str) -> str:
    text = pdf_to_text(path)
    if text:
        fname = path.stem[:80] + ".txt"
        data  = text.encode("utf-8", errors="ignore")
        ctype = "text/plain"
    else:
        fname = path.name
        data  = path.read_bytes()
        ctype = "application/pdf"

    try:
        r = requests.post(f"{OWUI_URL}/api/v1/files/", headers=_headers(),
                          files={"file": (fname, data, ctype)}, timeout=60)
        if r.status_code != 200:
            return f"upload {r.status_code}"
        file_id = r.json().get("id")
        if not file_id:
            return "no file_id"
        time.sleep(2)
        add = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/{collection_id}/file/add",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"file_id": file_id}, timeout=30,
        )
        if add.status_code == 400 and "Duplicate" in add.text:
            return "duplicate"
        return "ok" if add.status_code == 200 else f"add {add.status_code}"
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
