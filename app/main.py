import html
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.ai.router import AIRouter
from app.config import get_settings
from app.db import Database
from app.handlers import (
    consent_callback,
    delete_data_callback,
    delete_data_command,
    language_callback,
    legal_callback,
    newchat_callback,
    newchat_command,
    privacy_command,
    settings_command,
    start,
)

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO)
)
log = logging.getLogger(__name__)

WEBHOOK_URL = "https://ani-zeo-foundation.onrender.com/telegram/webhook"
ANILIST_URL = "https://graphql.anilist.co"

# Telegram messages have a 4096-character limit. Keep a margin for safety.
TELEGRAM_MESSAGE_LIMIT = 3500

WATCH_ORDER_PHRASES = (
    "watch order",
    "watching order",
    "order to watch",
    "chronological order",
    "release order",
)

SPECIFIC_ANIME_PHRASES = (
    "tell me about",
    "information about",
    "info about",
    "details about",
    "what is",
    "explain",
    "watch order",
    "watching order",
    "order to watch",
    "chronological order",
    "release order",
)


def extract_anime_search_term(user_text: str) -> Optional[str]:
    """
    Identify a likely specific anime/franchise request.
    Avoid image lookups for broad recommendation lists and casual chat.
    """
    original = re.sub(r"\s+", " ", user_text).strip()
    lowered = original.lower()

    if not any(phrase in lowered for phrase in SPECIFIC_ANIME_PHRASES):
        return None

    if any(
        phrase in lowered
        for phrase in (
            "recommend anime",
            "anime recommendations",
            "suggest anime",
            "top 5 anime",
            "top 10 anime",
            "anime like",
            "similar anime",
        )
    ):
        return None

    term = original

    # Remove common request prefixes.
    prefixes = (
        "tell me about ",
        "give me information about ",
        "give information about ",
        "information about ",
        "info about ",
        "details about ",
        "what is ",
        "explain ",
        "watch order for ",
        "watch order of ",
        "watching order for ",
        "watching order of ",
        "order to watch ",
        "chronological order of ",
        "release order of ",
    )
    for prefix in prefixes:
        if term.lower().startswith(prefix):
            term = term[len(prefix):].strip()
            break

    # Remove watch-order wording wherever it appears in the remaining title.
    for phrase in WATCH_ORDER_PHRASES:
        term = re.sub(re.escape(phrase), " ", term, flags=re.IGNORECASE)

    # Remove trailing request details, not title words.
    term = re.split(
        r"\b(with|including|include|in tenglish|in hinglish|in tanglish|"
        r"in english|in telugu|please|bro)\b",
        term,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    term = re.sub(r"\s+", " ", term).strip(" .?!,:;-")

    if not term or len(term) > 80:
        return None

    # Avoid searching for generic fragments.
    if term.lower() in {"anime", "series", "movies", "the anime"}:
        return None

    return term


async def find_anime_cover(title: str) -> Optional[dict]:
    """Fetch one matching anime cover from AniList."""
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        id
        title {
          romaji
          english
          native
        }
        coverImage {
          extraLarge
          large
        }
        siteUrl
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                ANILIST_URL,
                json={
                    "query": query,
                    "variables": {"search": title},
                },
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()

        media = payload.get("data", {}).get("Media")
        if not media:
            return None

        cover = media.get("coverImage") or {}
        image_url = cover.get("extraLarge") or cover.get("large")
        if not image_url:
            return None

        names = media.get("title") or {}
        display_title = (
            names.get("english")
            or names.get("romaji")
            or title
        )

        return {
            "title": display_title,
            "image_url": image_url,
            "source_url": media.get("siteUrl"),
        }

    except Exception as exc:
        # Image lookup is optional: an AniList outage must not stop the AI reply.
        log.warning("AniList cover lookup failed (%s)", type(exc).__name__)
        return None


def convert_markdown_table(lines: list[str]) -> list[str]:
    """
    Convert simple Markdown pipe tables into readable Telegram text.
    Telegram HTML does not support Markdown-style tables.
    """
    cleaned = []
    rows = []

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell or "-") for cell in cells):
            continue
        rows.append(cells)

    if not rows:
        return lines

    headers = rows[0]
    for row in rows[1:]:
        parts = []
        for index, value in enumerate(row):
            if not value:
                continue
            label = headers[index] if index < len(headers) else f"Column {index + 1}"
            parts.append(f"**{label}:** {value}")
        if parts:
            cleaned.append("• " + " · ".join(parts))

    return cleaned or ["Table information unavailable."]


def format_inline_markdown(text: str) -> str:
    """Escape text and convert common inline Markdown to Telegram HTML."""
    text = html.escape(text)

    code_placeholders = []

    def save_inline_code(match):
        code_placeholders.append(
            "<code>" + match.group(1) + "</code>"
        )
        return f"ANI_ZEO_CODE_{len(code_placeholders) - 1}_END"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)

    # Markdown links. Text has already been HTML-escaped.
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
        r'<a href="\2">\1</a>',
        text,
    )

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<i>\1</i>", text)

    for index, value in enumerate(code_placeholders):
        text = text.replace(f"ANI_ZEO_CODE_{index}_END", value)

    return text


def markdown_to_telegram_html(text: str) -> str:
    """Render headings, lists, tables and inline Markdown as Telegram HTML."""
    lines = text.splitlines()
    output = []
    index = 0
    in_code_block = False
    code_lines = []

    while index < len(lines):
        line = lines[index]

        if line.strip().startswith("```"):
            if in_code_block:
                output.append(
                    "<pre>" + html.escape("\n".join(code_lines)) + "</pre>"
                )
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            index += 1
            continue

        if in_code_block:
            code_lines.append(line)
            index += 1
            continue

        # Collect and convert a consecutive Markdown table.
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_lines = []
            while index < len(lines):
                candidate = lines[index].strip()
                if not (candidate.startswith("|") and candidate.endswith("|")):
                    break
                table_lines.append(lines[index])
                index += 1

            for table_line in convert_markdown_table(table_lines):
                output.append(format_inline_markdown(table_line))
            continue

        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+)$", line)
        if heading:
            output.append(
                "<b>" + format_inline_markdown(heading.group(1)) + "</b>"
            )
            index += 1
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if bullet:
            output.append(
                "• " + format_inline_markdown(bullet.group(1))
            )
            index += 1
            continue

        numbered = re.match(r"^\s*(\d+)[.)]\s+(.+)$", line)
        if numbered:
            output.append(
                numbered.group(1)
                + ". "
                + format_inline_markdown(numbered.group(2))
            )
            index += 1
            continue

        output.append(format_inline_markdown(line))
        index += 1

    if in_code_block:
        output.append(
            "<pre>" + html.escape("\n".join(code_lines)) + "</pre>"
        )

    return "\n".join(output)


def split_text_safely(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split plain Markdown at paragraph/line boundaries before formatting."""
    chunks = []
    current = ""

    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]

        if len(current) + len(line) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current += line

    if current:
        chunks.append(current)

    return chunks or [""]


async def send_formatted_answer(message, answer: str) -> None:
    """Send formatted answer chunks, falling back safely if Telegram rejects HTML."""
    for chunk in split_text_safely(answer):
        formatted = markdown_to_telegram_html(chunk)

        try:
            await message.reply_text(
                formatted,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as exc:
            log.warning(
                "Telegram formatted send failed (%s); using plain text",
                type(exc).__name__,
            )
            await message.reply_text(chunk)


async def chat_message(update: Update, context) -> None:
    message = update.effective_message
    user = update.effective_user

    if not message or not message.text or not user:
        return

    db = context.application.bot_data["db"]
    profile = await db.get_profile(user.id)

    if not profile or not profile.get("consented_at"):
        await message.reply_text(
            "Please use /start and review the consent information first."
        )
        return

    await db.save_message(user.id, "user", message.text)

    try:
        # Personalization can be disabled in the user's profile.
        personalization_enabled = profile.get("personalization_enabled", True) is not False
        memory_record = None
        summary_text = None
        summary_cursor = 0

        if personalization_enabled:
            memory_record = await db.get_memory(user.id)
            if memory_record:
                try:
                    memory_data = json.loads(memory_record)
                    summary_text = str(memory_data.get("summary") or "")[:1500]
                    summary_cursor = int(memory_data.get("last_id") or 0)
                except (ValueError, TypeError, AttributeError):
                    # Migrate an older plain-text memory value safely.
                    summary_text = str(memory_record)[:1500]

        history = await db.get_recent_messages(user.id, limit=8)

        # Look up a single cover only for a specific anime/franchise question.
        search_term = extract_anime_search_term(message.text)
        anime_cover = (
            await find_anime_cover(search_term)
            if search_term
            else None
        )

        answer, provider = await context.application.bot_data["ai"].reply(
            history,
            profile.get("preferred_language"),
            memory_summary=summary_text,
        )

        await db.save_message(user.id, "assistant", answer)
        log.info("AI reply completed via provider=%s", provider)

        if anime_cover:
            try:
                await message.reply_photo(
                    photo=anime_cover["image_url"],
                    caption=f"🎌 {anime_cover['title']}",
                )
            except Exception as exc:
                log.warning(
                    "Telegram anime cover send failed (%s)",
                    type(exc).__name__,
                )

        await send_formatted_answer(message, answer)

        # Refresh memory after the user has received the answer. Summarization is
        # best-effort: if it fails, the chat reply remains successful.
        if personalization_enabled:
            try:
                pending = await db.get_messages_for_summary(
                    user.id,
                    after_id=summary_cursor,
                    keep_recent=8,
                    limit=24,
                )
                if len(pending) >= 8:
                    ai = context.application.bot_data["ai"]
                    updated_summary = await ai.summarize_memory(
                        summary_text,
                        pending,
                    )
                    if updated_summary:
                        last_id = int(pending[-1]["id"])
                        await db.set_memory(
                            user.id,
                            json.dumps(
                                {"summary": updated_summary, "last_id": last_id},
                                ensure_ascii=False,
                            ),
                        )
                        log.info("Conversation memory summary updated.")
            except Exception as memory_exc:
                log.warning(
                    "Conversation memory update skipped (%s)",
                    type(memory_exc).__name__,
                )

    except Exception as exc:
        log.warning(
            "AI response failed (%s)",
            type(exc).__name__,
        )
        await message.reply_text(
            "I'm having trouble reaching my AI providers right now. "
            "Please try again shortly."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(settings)
    await db.connect()

    telegram_app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    telegram_app.bot_data["db"] = db
    telegram_app.bot_data["ai"] = AIRouter(settings)

    # Commands
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(
        CommandHandler("settings", settings_command)
    )
    telegram_app.add_handler(
        CommandHandler("newchat", newchat_command)
    )
    telegram_app.add_handler(
        CommandHandler("privacy", privacy_command)
    )
    telegram_app.add_handler(
        CommandHandler("delete_my_data", delete_data_command)
    )

    # Callback handlers
    telegram_app.add_handler(
        CallbackQueryHandler(legal_callback, pattern=r"^legal:")
    )
    telegram_app.add_handler(
        CallbackQueryHandler(consent_callback, pattern=r"^consent:")
    )
    telegram_app.add_handler(
        CallbackQueryHandler(language_callback, pattern=r"^lang:")
    )
    telegram_app.add_handler(
        CallbackQueryHandler(newchat_callback, pattern=r"^newchat:")
    )
    telegram_app.add_handler(
        CallbackQueryHandler(
            delete_data_callback,
            pattern=r"^delete_data:",
        )
    )

    # Normal text messages
    telegram_app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat_message,
        )
    )

    await telegram_app.initialize()

    # Register Telegram webhook automatically.
    await telegram_app.bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=settings.webhook_secret,
        allowed_updates=Update.ALL_TYPES,
    )

    log.info("Telegram webhook registered successfully.")
    await telegram_app.start()

    app.state.db = db
    app.state.telegram_app = telegram_app

    try:
        yield
    finally:
        await telegram_app.stop()
        await telegram_app.shutdown()
        await db.close()


app = FastAPI(
    title="Ani Zeo",
    lifespan=lifespan,
)


@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": "ani-zeo",
    }


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )

    if not secret or secret != settings.webhook_secret:
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )

    try:
        payload = await request.json()
        telegram_app = request.app.state.telegram_app

        update = Update.de_json(
            payload,
            telegram_app.bot,
        )

        if update is None or update.update_id is None:
            raise HTTPException(status_code=400, detail="Invalid update")

        db = request.app.state.db
        claimed = await db.claim_telegram_update(update.update_id)

        if not claimed:
            log.info("Duplicate Telegram update ignored (update_id=%s)", update.update_id)
            return {"ok": True, "duplicate": True}

        try:
            await telegram_app.process_update(update)
            await db.complete_telegram_update(update.update_id)
        except Exception as exc:
            await db.fail_telegram_update(
                update.update_id,
                f"dispatch_{type(exc).__name__}",
            )
            log.warning(
                "Webhook update processing failed (type=%s)",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="Update processing failed",
            )

    except HTTPException:
        raise
    except Exception as exc:
        log.warning(
            "Webhook update rejected (%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid update",
        )

    return {"ok": True}
