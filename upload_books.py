#!/usr/bin/env python3
"""Upload all PDFs in a folder to Open WebUI as text — no copying, no classification."""
import os
import sys
import time
from pathlib import Path

import requests

OWUI_URL = os.getenv("OPENWEBUI_URL", "http://100.126.22.55:3001")
OWUI_KEY = os.getenv("OPENWEBUI_API_KEY", "")
KB_ID    = os.getenv("KB_ID", "52855bbd-d8b9-43ed-b637-e1722959cfb9")


def pdf_to_text(path: Path) -> str | None:
    try:
        import fitz
        doc = fitz.open(str(path))
        pages = [p.get_text() for p in doc if p.get_text().strip()]
        doc.close()
        return "\n\n".join(pages) or None
    except Exception:
        return None


def upload(path: Path) -> str:
    h = {"Authorization": f"Bearer {OWUI_KEY}"}
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
        r = requests.post(f"{OWUI_URL}/api/v1/files/", headers=h,
                          files={"file": (fname, data, ctype)}, timeout=60)
        if r.status_code != 200:
            return f"upload {r.status_code}"
        file_id = r.json().get("id")
        if not file_id:
            return "no file_id"
        time.sleep(2)
        add = requests.post(
            f"{OWUI_URL}/api/v1/knowledge/{KB_ID}/file/add",
            headers={**h, "Content-Type": "application/json"},
            json={"file_id": file_id}, timeout=30,
        )
        if add.status_code == 400 and "Duplicate" in add.text:
            return "duplicate (already in collection)"
        return "ok" if add.status_code == 200 else f"add {add.status_code}"
    except Exception as e:
        return f"error: {e}"


def main():
    if not OWUI_KEY:
        print("Set OPENWEBUI_API_KEY env var first.")
        sys.exit(1)

    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Books" / "AI-Library"
    pdfs = sorted(folder.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {folder}")
    print(f"Uploading to Open WebUI collection {KB_ID}\n")

    ok = fail = 0
    for i, path in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {path.name[:60]}", end=" ... ", flush=True)
        result = upload(path)
        print(result)
        if result in ("ok", "duplicate (already in collection)"):
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} uploaded, {fail} failed")


if __name__ == "__main__":
    main()
