"""Unified Knowledge Bot — 2-hour Telegram lessons from YouTube + Books, plus /ask Q&A."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import random

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler, ContextTypes

import fts

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID", ""))
OWUI_URL = os.getenv("OPENWEBUI_URL", "http://100.126.22.55:3001")
OWUI_KEY = os.getenv("OPENWEBUI_API_KEY", "")
KB_ALL = os.getenv("KB_ALL", "")
LESSON_INTERVAL_HOURS = int(os.getenv("LESSON_INTERVAL_HOURS", "2"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_claude = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


def _claude_complete(prompt: str, system: str = "") -> str:
    """Call Claude Haiku. Returns text response."""
    kwargs: dict = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    msg = _claude.messages.create(**kwargs)
    return msg.content[0].text.strip()

_H = html.escape  # shorthand for HTML escaping user content


def _guard(update: Update) -> bool:
    return update.effective_user is not None and str(update.effective_user.id) == CHAT_ID


# ── Lesson formatting ──────────────────────────────────────────────────────────

def _format_video_lesson(entry: dict) -> str:
    topic = entry.get("topic", "")
    subtopic = entry.get("subtopic", "")
    title = entry.get("title") or "Untitled"
    channel = entry.get("channel") or ""
    key_points = entry.get("key_points") or []
    takeaways = entry.get("takeaways") or []
    quotes = entry.get("quotes") or []
    url = entry.get("url") or ""

    cat = f"{topic} › {subtopic}" if subtopic else topic
    lines = [f"🧠 <b>Knowledge Lesson</b>"]
    if cat:
        lines.append(f"<i>{_H(cat)}</i>")
    lines += ["", f"📺 <b>{_H(title)}</b>"]
    if channel:
        lines.append(f"Channel: {_H(channel)}")

    if key_points:
        lines += ["", f"💡 <b>Key insight:</b>\n{_H(key_points[0])}"]
    if takeaways:
        lines += ["", f"🎯 <b>Takeaway:</b>\n{_H(takeaways[0])}"]
    if quotes:
        lines += ["", f'📝 <i>"{_H(quotes[0])}"</i>']
    if url:
        lines += ["", f"🔗 {url}"]

    lines += ["", "/ask anything · /tree browse topics · /stats"]
    return "\n".join(lines)


def _collection_has_files(kb_id: str) -> bool:
    """Return True if the OpenWebUI knowledge collection has at least one file."""
    try:
        r = requests.get(
            f"{OWUI_URL}/api/v1/knowledge/{kb_id}",
            headers={"Authorization": f"Bearer {OWUI_KEY}"},
            timeout=10,
        )
        data = r.json()
        files = data.get("files") or []
        return len(files) > 0
    except Exception:
        return False


def _get_book_lesson() -> str | None:
    """Ask OpenWebUI RAG to deliver one lesson from the book library."""
    if not OWUI_KEY or not KB_ALL:
        return None
    if not _collection_has_files(KB_ALL):
        log.info("book lesson skipped — collection empty, upload books to Open WebUI first")
        return None
    prompt = (
        "From one of the books in this library, teach me one profound insight. "
        "Use ONLY content from the provided documents. Format your response EXACTLY as:\n"
        "BOOK: [title]\n"
        "INSIGHT: [the key idea in 2-3 sentences]\n"
        "QUOTE: [one exact quote from the book, or leave blank]\n"
        "ACTION: [one concrete thing to do with this knowledge]\n"
        "Total length: under 150 words."
    )
    try:
        # Fetch relevant book passages from OpenWebUI RAG, then let Claude format the lesson
        rag_resp = requests.post(
            f"{OWUI_URL}/api/chat/completions",
            headers={"Authorization": f"Bearer {OWUI_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "Give me one key passage or insight from any book in this collection. Return the book title and exact text."}],
                "files": [{"type": "collection", "id": KB_ALL}],
            },
            timeout=120,
        )
        rag_resp.raise_for_status()
        book_passage = rag_resp.json()["choices"][0]["message"]["content"]

        if _claude:
            raw = _claude_complete(
                prompt + f"\n\nBook passage to teach from:\n{book_passage}",
                system="You are a personal knowledge tutor. Format lessons clearly and concisely.",
            )
        else:
            raw = book_passage

        def _field(key: str) -> str:
            import re
            m = re.search(rf"^{key}:\s*(.+?)(?=\n[A-Z]+:|$)", raw, re.MULTILINE | re.DOTALL)
            return m.group(1).strip() if m else ""

        book = _field("BOOK")
        insight = _field("INSIGHT")
        quote = _field("QUOTE")
        action = _field("ACTION")

        lines = ["📚 <b>Knowledge Lesson — From Your Library</b>"]
        if book:
            lines += ["", f"📖 <b>{_H(book)}</b>"]
        if insight:
            lines += ["", f"💡 <b>Insight:</b>\n{_H(insight)}"]
        if action:
            lines += ["", f"🎯 <b>Action:</b>\n{_H(action)}"]
        if quote:
            lines += ["", f'📝 <i>"{_H(quote)}"</i>']
        lines += ["", "/ask anything · /tree browse topics · /stats"]
        return "\n".join(lines)

    except Exception as exc:
        log.warning("book lesson failed: %s", exc)
        return None


async def send_lesson(app: Application) -> None:
    """Pick a lesson (70% video / 30% book) and push to Telegram."""
    use_book = KB_ALL and OWUI_KEY and random.random() < 0.3

    msg: str | None = None
    source = "video"

    if use_book:
        msg = await asyncio.to_thread(_get_book_lesson)
        if msg:
            source = "book"

    if not msg:
        entry = await asyncio.to_thread(fts.get_lesson_candidate)
        if not entry:
            log.info("lesson skipped — no candidates in library yet")
            return
        msg = _format_video_lesson(entry)
        await asyncio.to_thread(fts.mark_lesson_sent, entry["id"])

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=msg,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    log.info("lesson sent (source=%s)", source)


# ── Q&A ────────────────────────────────────────────────────────────────────────

def _ykl_context(question: str) -> str:
    results = fts.search(question, limit=4)
    if not results:
        return ""
    parts = []
    for r in results:
        pts = (r.get("key_points") or [])[:3]
        pts_text = "\n".join(f"  - {p}" for p in pts)
        parts.append(f"[YouTube: {r.get('title', '')}]\n{pts_text}")
    return "\n\n".join(parts)


def _book_context(question: str) -> str:
    if not OWUI_KEY or not KB_ALL:
        return ""
    if not _collection_has_files(KB_ALL):
        return ""
    try:
        resp = requests.post(
            f"{OWUI_URL}/api/chat/completions",
            headers={"Authorization": f"Bearer {OWUI_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama3.2:3b",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract relevant passages from the provided documents that help answer "
                            "the question. ONLY use document content, never your training data."
                        ),
                    },
                    {"role": "user", "content": question},
                ],
                "files": [{"type": "collection", "id": KB_ALL}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        log.warning("book context failed: %s", exc)
        return ""


def _synthesize_answer(question: str, ykl_ctx: str, book_ctx: str) -> str:
    if not ykl_ctx and not book_ctx:
        return "Nothing found in your knowledge base. Add more videos or books and try again."

    sections = []
    if ykl_ctx:
        sections.append(f"=== FROM YOUR YOUTUBE LIBRARY ===\n{ykl_ctx}")
    if book_ctx:
        sections.append(f"=== FROM YOUR BOOKS ===\n{book_ctx}")
    context = "\n\n".join(sections)

    prompt = (
        f"Question: {question}\n\n"
        f"Use ONLY the following knowledge from the user's personal library to answer:\n\n"
        f"{context}\n\n"
        "Give a clear, direct answer. Mention which video or book the insight came from. "
        "If the knowledge base doesn't cover it, say so explicitly. "
        "Be concise — under 300 words."
    )

    if _claude:
        try:
            return _claude_complete(
                prompt,
                system="You are a personal knowledge assistant. Answer only from the provided library content.",
            )
        except Exception as exc:
            log.warning("Claude failed, falling back to Ollama: %s", exc)

    # Ollama fallback
    ollama_url = "http://100.126.22.55:11434"
    for model, timeout in [("hermes3:70b", 180), ("qwen3.5:latest", 120), ("llama3.2:3b", 60)]:
        try:
            resp = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()
        except Exception:
            continue

    return "LLM unavailable. Raw context:\n\n" + context[:800]


# ── Telegram handlers ──────────────────────────────────────────────────────────

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _guard(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ask <your question>")
        return

    question = " ".join(context.args)
    status = await update.message.reply_text("🔍 Searching your knowledge base...")

    ykl_ctx, book_ctx = await asyncio.gather(
        asyncio.to_thread(_ykl_context, question),
        asyncio.to_thread(_book_context, question),
    )
    answer = await asyncio.to_thread(_synthesize_answer, question, ykl_ctx, book_ctx)

    text = f"🧠 <b>Answer</b>\n\n{_H(answer)}"
    if len(text) > 4000:
        text = text[:4000] + "…"
    await status.edit_text(text, parse_mode="HTML")


async def cmd_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _guard(update):
        return
    await update.message.reply_text("📚 Picking a lesson from your library...")
    await send_lesson(context.application)


async def cmd_tree(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _guard(update):
        return
    tree = await asyncio.to_thread(fts.get_tree)
    if not tree:
        await update.message.reply_text("Library is empty. Paste some YouTube URLs first.")
        return

    lines = ["📊 <b>Knowledge Tree</b>\n"]
    for topic in sorted(tree):
        subtopics = tree[topic]
        total = sum(subtopics.values())
        lines.append(f"<b>{_H(topic)}</b> ({total} videos)")
        for sub, count in sorted(subtopics.items(), key=lambda x: -x[1]):
            lines.append(f"  ├ {_H(sub)}: {count}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _guard(update):
        return
    stats = await asyncio.to_thread(fts.get_stats)
    text = (
        "📈 <b>Knowledge Base Stats</b>\n\n"
        f"📺 YouTube videos: {stats['total_videos']}\n"
        f"🗂 Topics: {stats['topics']}\n"
        f"🧠 Lessons delivered: {stats['lessons_sent']}\n"
        f"⏰ Lessons every {LESSON_INTERVAL_HOURS}h"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _guard(update):
        return
    text = (
        "🧠 <b>Knowledge Bot</b>\n\n"
        "/ask &lt;question&gt; — search all videos + books and synthesize an answer\n"
        "/lesson — get a lesson right now\n"
        "/tree — browse your knowledge by topic\n"
        "/stats — library stats\n\n"
        f"Auto-lessons push every {LESSON_INTERVAL_HOURS}h from YouTube library + books."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def _lesson_job(context: CallbackContext) -> None:
    await send_lesson(context.application)


def main() -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in .env")

    fts.init_fts()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("lesson", cmd_lesson))
    app.add_handler(CommandHandler("tree", cmd_tree))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # 2-hour auto-lesson (first fires 60s after start to confirm bot is live)
    app.job_queue.run_repeating(
        _lesson_job,
        interval=LESSON_INTERVAL_HOURS * 3600,
        first=60,
    )

    log.info("Knowledge bot starting — lessons every %dh", LESSON_INTERVAL_HOURS)
    app.run_polling()


if __name__ == "__main__":
    main()
