#!/usr/bin/env python3
"""
Sort PDFs in AI-Library into category subfolders using filename heuristics.
Run on Mac. After sorting, rsync the folder to base.

Usage:
    python3 sort_books.py [--folder ~/Books/AI-Library]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

CATEGORIES = {
    "cybersecurity": [
        "hack", "pentest", "security", "exploit", "malware", "oscp", "ctf",
        "forensic", "cyber", "vulnerability", "kali", "metasploit", "burp",
        "nmap", "wireshark", "reverse", "shellcode", "overflow", "injection",
        "owasp", "cryptography", "crypto", "cipher", "encryption", "nist",
        "incident", "threat", "attack", "defense", "firewall", "intrusion",
    ],
    "networking": [
        "network", "tcp", "ip", "dns", "http", "packet", "protocol",
        "routing", "switching", "cisco", "bgp", "ospf", "vlan", "vpn",
        "wireless", "wifi", "802", "subnet", "socket",
    ],
    "linux": [
        "linux", "unix", "bash", "shell", "ubuntu", "debian", "kernel",
        "command line", "cli", "sysadmin", "systemd", "gnu",
    ],
    "programming": [
        "python", "javascript", "java", "golang", "rust", "c++", "algorithm",
        "data structure", "design pattern", "software", "programming", "coding",
        "developer", "engineering", "api", "database", "sql", "web", "react",
        "django", "flask", "selenium", "testing", "clean code", "refactor",
        "objective-c", "swift",
    ],
    "investing": [
        "invest", "finance", "money", "wealth", "crypto", "trading", "stock",
        "portfolio", "budget", "financial", "retirement", "passive income",
        "real estate", "economics", "blockchain",
    ],
    "self_improvement": [
        "habit", "mindset", "productivity", "atomic", "discipline", "stoic",
        "motivation", "focus", "deep work", "psychology", "mental", "learning",
        "memory", "leadership", "communication", "negotiat",
    ],
    "fitness": [
        "fitness", "nutrition", "diet", "running", "sleep", "muscle",
        "workout", "exercise", "health", "weight", "body", "training",
    ],
    "business": [
        "business", "startup", "entrepreneur", "management", "marketing",
        "sales", "strategy", "product", "growth", "lean", "agile",
    ],
}


def classify(path: Path) -> str:
    name = path.stem.lower()
    try:
        import fitz
        doc = fitz.open(str(path))
        meta = doc.metadata or {}
        title = (meta.get("title") or "").lower()
        doc.close()
        name = name + " " + title
    except Exception:
        pass

    for category, keywords in CATEGORIES.items():
        if any(kw in name for kw in keywords):
            return category
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sort PDFs into category subfolders")
    parser.add_argument("--folder", type=Path,
                        default=Path.home() / "Books" / "AI-Library")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would move without moving")
    args = parser.parse_args()

    folder = args.folder
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return

    # Find only PDFs directly in folder (not already in subfolders)
    pdfs = [p for p in folder.glob("*.pdf")]
    print(f"Found {len(pdfs)} PDFs to sort in {folder}\n")

    counts: dict[str, int] = {}
    for pdf in pdfs:
        cat = classify(pdf)
        dest_dir = folder / cat
        dest = dest_dir / pdf.name
        counts[cat] = counts.get(cat, 0) + 1

        if args.dry_run:
            print(f"  [{cat:20}] {pdf.name[:60]}")
        else:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(pdf), str(dest))
            print(f"  → {cat:20}  {pdf.name[:55]}")

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Summary:")
    for cat, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:20} {n} books")

    if not args.dry_run:
        print(f"\nDone. Subfolders created in {folder}")
        print("\nNext — sync to base:")
        print(f"  rsync -av --progress {folder}/ base:~/Books/AI-Library/")
        print("\nThen on base:")
        print("  cd ~/projects/youtube-knowledge-library")
        print("  python3 upload_books_by_category.py")


if __name__ == "__main__":
    main()
