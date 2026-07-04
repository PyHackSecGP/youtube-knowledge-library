#!/usr/bin/env python3
"""
Book Curator — scan Mac for PDFs, AI recommends which go to knowledge base,
you approve, approved books move to ~/Books/AI-Library + upload to Open WebUI.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

import requests

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False

# ── Config (edit these) ───────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENWEBUI_URL     = os.getenv("OPENWEBUI_URL", "http://100.126.22.55:3001")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
KB_ID             = os.getenv("KB_ID", "52855bbd-d8b9-43ed-b637-e1722959cfb9")  # cybersecurity-books

AI_LIBRARY_DIR = Path.home() / "Books" / "AI-Library"   # approved books land here
ARCHIVE_DIR    = Path.home() / "Books" / "Archive"       # everything else
CACHE_FILE     = Path.home() / ".book_curator_cache.json"

MIN_PAGES = 20
MIN_SIZE_KB = 300

SKIP_PATHS = {
    str(Path.home() / "Library"),
    str(Path.home() / ".Trash"),
    str(Path.home() / ".cache"),
    "/System", "/usr", "/private", "/Volumes/Macintosh HD",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def file_hash(path: Path) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            h.update(f.read(131072))
    except OSError:
        return ""
    return h.hexdigest()


def pdf_metadata(path: Path) -> dict:
    try:
        import fitz
        doc = fitz.open(str(path))
        meta = doc.metadata or {}
        pages = doc.page_count
        doc.close()
        return {
            "title":  (meta.get("title") or "").strip()[:200],
            "author": (meta.get("author") or "").strip()[:200],
            "pages":  pages,
            "size_mb": round(path.stat().st_size / 1_048_576, 1),
        }
    except Exception:
        try:
            size_mb = round(path.stat().st_size / 1_048_576, 1)
        except Exception:
            size_mb = 0
        return {"title": "", "author": "", "pages": 0, "size_mb": size_mb}


def get_mounted_drives() -> list[Path]:
    """Return extra scan roots from mounted drives (Mac /Volumes, Linux /media + /mnt)."""
    roots: list[Path] = []
    if platform.system() == "Darwin":
        volumes = Path("/Volumes")
        if volumes.exists():
            for v in volumes.iterdir():
                p = str(v)
                if not any(p.startswith(s) for s in SKIP_PATHS):
                    roots.append(v)
    else:
        for base in [Path("/media"), Path("/mnt")]:
            if base.exists():
                roots.extend(base.iterdir())
    return roots


def find_pdfs(scan_paths: list[Path]) -> list[Path]:
    pdfs = []
    for root in scan_paths:
        if not root.exists():
            continue
        print(f"  Scanning {root} ...")
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dp = Path(dirpath)
            path_str = str(dp)
            if any(path_str.startswith(s) for s in SKIP_PATHS):
                dirnames.clear()
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                if fname.lower().endswith(".pdf"):
                    pdfs.append(dp / fname)
    return pdfs


# ── Claude classification ─────────────────────────────────────────────────────

PROMPT = """You are reviewing a PDF to decide if it belongs in a cybersecurity professional's AI knowledge base.

File: {filename}
Title: {title}
Author: {author}
Pages: {pages}
Size: {size_mb}MB

The knowledge base is for learning: cybersecurity, hacking, networking, Linux, programming, investing, personal development, fitness, productivity, business.

Reply with EXACTLY this JSON (no other text):
{{
  "keep": true/false,
  "category": "one of: cybersecurity | networking | linux | programming | investing | self_improvement | fitness | business | other",
  "reason": "one sentence why"
}}

Rules:
- keep=true: real books (20+ pages) on any of the learning topics above
- keep=false: fiction, receipts, invoices, forms, man pages, tool docs under 20 pages, scanned documents, children books"""


def claude_classify(path: Path, meta: dict) -> dict:
    if not ANTHROPIC_API_KEY:
        return _heuristic(path, meta)
    prompt = PROMPT.format(
        filename=path.name,
        title=meta["title"] or "(none)",
        author=meta["author"] or "(none)",
        pages=meta["pages"],
        size_mb=meta["size_mb"],
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "system": "Return only valid JSON, no markdown, no explanation.",
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        return json.loads(text)
    except Exception:
        return _heuristic(path, meta)


def _heuristic(path: Path, meta: dict) -> dict:
    name = (path.name + " " + meta["title"]).lower()
    cyber = ["hack", "pentest", "security", "exploit", "malware", "oscp", "ctf", "forensic", "cyber"]
    tech  = ["linux", "python", "programming", "network", "algorithm", "code", "software"]
    money = ["invest", "finance", "money", "wealth", "crypto", "trading"]
    self_ = ["habit", "mindset", "productivity", "atomic", "discipline", "stoic"]
    fit   = ["fitness", "nutrition", "diet", "running", "sleep", "muscle"]

    if any(k in name for k in cyber):
        return {"keep": True, "category": "cybersecurity", "reason": "cybersecurity keyword match"}
    if any(k in name for k in tech):
        return {"keep": True, "category": "programming", "reason": "tech keyword match"}
    if any(k in name for k in money):
        return {"keep": True, "category": "investing", "reason": "finance keyword match"}
    if any(k in name for k in self_):
        return {"keep": True, "category": "self_improvement", "reason": "self-help keyword match"}
    if any(k in name for k in fit):
        return {"keep": True, "category": "fitness", "reason": "fitness keyword match"}
    return {"keep": False, "category": "other", "reason": "no relevant keywords found"}


# ── Open WebUI upload ─────────────────────────────────────────────────────────

def upload_to_openwebui(path: Path) -> bool:
    headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}
    try:
        with open(path, "rb") as f:
            upload = requests.post(
                f"{OPENWEBUI_URL}/api/v1/files/",
                headers=headers,
                files={"file": (path.name, f, "application/pdf")},
                timeout=120,
            )
        if upload.status_code != 200:
            print(f"    [upload error] {upload.status_code}: {upload.text[:100]}")
            return False
        file_id = upload.json().get("id")
        if not file_id:
            return False

        time.sleep(2)  # let Open WebUI process the file

        add = requests.post(
            f"{OPENWEBUI_URL}/api/v1/knowledge/{KB_ID}/file/add",
            headers={**headers, "Content-Type": "application/json"},
            json={"file_id": file_id},
            timeout=30,
        )
        if add.status_code == 400 and "Duplicate" in add.text:
            return True  # already in collection
        return add.status_code == 200
    except Exception as e:
        print(f"    [upload failed] {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def safe_move(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    shutil.copy2(src, dest)
    return dest


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Book curator — find, approve, upload PDFs to Open WebUI")
    parser.add_argument("--scan", nargs="+", type=Path, default=[Path.home()],
                        help="Folders to scan (default: home)")
    parser.add_argument("--drives", action="store_true",
                        help="Also scan all mounted drives (Mac /Volumes, Linux /media /mnt)")
    parser.add_argument("--reset-cache", action="store_true", help="Re-classify everything")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Skip interactive approval — approve all recommended books")
    args = parser.parse_args()

    if args.drives:
        extra = get_mounted_drives()
        if extra:
            print(f"  Mounted drives found: {[str(e) for e in extra]}")
        args.scan = list(args.scan) + extra

    print("=" * 60)
    print("Book Curator")
    print(f"  Scanning:    {[str(p) for p in args.scan]}")
    print(f"  AI Library:  {AI_LIBRARY_DIR}")
    print(f"  Archive:     {ARCHIVE_DIR}")
    print(f"  Open WebUI:  {OPENWEBUI_URL}")
    print("=" * 60)

    # Find all PDFs
    print("\nFinding PDFs...")
    all_pdfs = find_pdfs(args.scan)
    print(f"Found {len(all_pdfs)} PDFs\n")

    if not all_pdfs:
        print("No PDFs found. Check the scan path.")
        return

    # Classify
    cache = {} if args.reset_cache else load_cache()
    candidates: list[dict] = []  # books Claude says keep=True
    skipped = 0
    seen_hashes: set[str] = set()

    print("Classifying with Claude...")
    _iter = tqdm(enumerate(all_pdfs, 1), total=len(all_pdfs), unit="pdf") if _HAS_TQDM \
        else enumerate(all_pdfs, 1)
    for i, path in _iter:
        if not _HAS_TQDM:
            print(f"  [{i}/{len(all_pdfs)}] {path.name[:60]}", end=" ", flush=True)

        def _log(msg: str) -> None:
            if _HAS_TQDM:
                tqdm.write(f"  {path.name[:55]}  {msg}")
            else:
                print(msg)

        # Dedup
        h = file_hash(path)
        if h and h in seen_hashes:
            _log("→ duplicate")
            continue
        if h:
            seen_hashes.add(h)

        # Size/page pre-filter
        try:
            size_kb = path.stat().st_size / 1024
            if size_kb < MIN_SIZE_KB:
                _log("→ too small")
                skipped += 1
                continue
        except Exception:
            pass

        # Classify (cache hit or Claude)
        key = str(path)
        if key in cache and not args.reset_cache:
            result = cache[key]["result"]
            _log(f"→ {result['category']} (cached)")
        else:
            meta = pdf_metadata(path)
            if meta["pages"] > 0 and meta["pages"] < MIN_PAGES:
                _log(f"→ skip ({meta['pages']} pages)")
                skipped += 1
                continue
            result = claude_classify(path, meta)
            cache[key] = {"result": result, "meta": meta}
            save_cache(cache)
            _log(f"→ {'✓ ' + result['category'] if result['keep'] else '✗ skip'}")

        if result["keep"]:
            meta = cache[key].get("meta", pdf_metadata(path))
            candidates.append({"path": path, "result": result, "meta": meta})

    print(f"\nClassified {len(all_pdfs)} books → {len(candidates)} recommended, {skipped} skipped\n")

    if not candidates:
        print("No books recommended for the AI library.")
        return

    # Interactive approval
    approved: list[dict] = []
    rejected: list[dict] = []

    if args.auto_approve:
        approved = candidates
        print(f"Auto-approving all {len(candidates)} recommended books.\n")
    else:
        print("=" * 60)
        print(f"REVIEW — {len(candidates)} books recommended")
        print("Commands: y=yes  n=no  a=approve all remaining  q=quit")
        print("=" * 60)

        for i, item in enumerate(candidates, 1):
            path   = item["path"]
            result = item["result"]
            meta   = item["meta"]
            title  = meta["title"] or path.stem
            author = f" by {meta['author']}" if meta["author"] else ""

            print(f"\n[{i}/{len(candidates)}] {title}{author}")
            print(f"  File:     {path.name}")
            print(f"  Category: {result['category']}")
            print(f"  Pages:    {meta['pages']}  |  Size: {meta['size_mb']}MB")
            print(f"  Reason:   {result['reason']}")

            while True:
                choice = input("  Add to AI Library? [y/n/a/q] > ").strip().lower()
                if choice in ("y", ""):
                    approved.append(item)
                    print("  ✓ Approved")
                    break
                elif choice == "n":
                    rejected.append(item)
                    print("  ✗ Skipped")
                    break
                elif choice == "a":
                    approved.extend(candidates[i-1:])
                    rejected_remaining = []
                    print(f"  ✓ Approved all remaining ({len(candidates) - i + 1} books)")
                    goto_upload = True
                    break
                elif choice == "q":
                    print("\nQuitting. Nothing moved yet.")
                    save_cache(cache)
                    return
            else:
                continue
            if choice == "a":
                break

    # Move + upload
    print(f"\n{'='*60}")
    print(f"Moving {len(approved)} approved books → {AI_LIBRARY_DIR}")
    print(f"Moving {len(rejected)} rejected books → {ARCHIVE_DIR}")
    print("=" * 60)

    uploaded = 0
    failed_upload = 0

    for item in approved:
        path = item["path"]
        dest = safe_move(path, AI_LIBRARY_DIR)
        print(f"\n  ✓ Copied:   {path.name[:55]}")
        print(f"    → {dest}")
        print(f"    Uploading to Open WebUI...", end=" ", flush=True)
        ok = upload_to_openwebui(dest)
        if ok:
            uploaded += 1
            print("✓ uploaded")
        else:
            failed_upload += 1
            print("✗ upload failed (file is in AI-Library folder)")

    for item in rejected:
        path = item["path"]
        dest = safe_move(path, ARCHIVE_DIR)
        print(f"  → Archive: {path.name[:55]}")

    # Summary
    print(f"\n{'='*60}")
    print("DONE")
    print(f"  Approved & copied:   {len(approved)}")
    print(f"  Uploaded to Open WebUI: {uploaded}")
    print(f"  Upload failures:     {failed_upload}")
    print(f"  Archived:            {len(rejected)}")
    print(f"\n  AI Library → {AI_LIBRARY_DIR}")
    print(f"  Archive    → {ARCHIVE_DIR}")
    print(f"  Open WebUI → {OPENWEBUI_URL}")
    print("=" * 60)

    save_cache(cache)


if __name__ == "__main__":
    main()
