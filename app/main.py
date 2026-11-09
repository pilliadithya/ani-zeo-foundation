import asyncio
import html
import json
import logging
import re
import secrets
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
from app.ai.fact_verifier import validate_generated_answer, verification_fallback
from app.ai.research import AnimeResearchService, REDIRECT
from app.config import get_settings
from app.db import Database
from app.handlers import (
    ai_usage_command,
    handle_onboarding_name,
    greeting_for_language,
    language_keyboard,
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
# HTTPX logs full request URLs. Telegram Bot API URLs contain the bot token,
# so keep transport-level request logging disabled in every environment.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

WEBHOOK_URL = "https://ani-zeo-foundation.onrender.com/telegram/webhook"
ANILIST_URL = "https://graphql.anilist.co"

# Telegram messages have a 4096-character limit. Keep a margin for safety.
TELEGRAM_MESSAGE_LIMIT = 3500
MAX_WEBHOOK_BODY_BYTES = 1_048_576
WEBHOOK_PROCESSING_TIMEOUT_SECONDS = 120

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
        return f"ANIZEOCODETOKEN{len(code_placeholders) - 1}END"

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
        text = text.replace(f"ANIZEOCODETOKEN{index}END", value)

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


async def telegram_error_handler(update: object, context) -> None:
    """Record uncaught PTB handler errors so the webhook can request a retry."""
    update_id = getattr(update, "update_id", None)
    if update_id is not None:
        context.application.bot_data.setdefault("failed_update_ids", set()).add(update_id)

    error = getattr(context, "error", None)
    log.error(
        "Telegram handler failed (update_id=%s, error_type=%s)",
        update_id,
        type(error).__name__ if error else "unknown",
    )


async def chat_message(update: Update, context) -> None:
    message = update.effective_message
    user = update.effective_user

    if not message or not message.text or not user:
        return

    db = context.application.bot_data["db"]
    profile = await db.get_profile(user.id)

    # Complete the two short onboarding steps before normal chat handling.
    if profile and profile.get("onboarding_step") == "awaiting_name":
        if await handle_onboarding_name(update, context):
            return

    if profile and profile.get("onboarding_step") == "awaiting_language":
        await message.reply_text(
            "Choose the language you'd like Ani Zeo to use:",
            reply_markup=language_keyboard(),
        )
        return

    if not profile or not profile.get("consented_at"):
        await message.reply_text(
            "Please use /start to read the welcome note and begin onboarding."
        )
        return

    research = context.application.bot_data["research"]
    recent_for_scope = await db.get_recent_messages(user.id, limit=6)
    intent_result = research.detect_intent(message.text, recent_for_scope)
    scope = intent_result["scope"]
    normalized_text = intent_result["normalized_text"]

    if intent_result["was_corrected"]:
        log.info(
            "Intent typo correction applied (intent=%s)",
            intent_result["intent"],
        )

    log.info(
        "Intent detected (intent=%s, scope=%s, confidence=%.2f)",
        intent_result["intent"],
        scope,
        intent_result["confidence"],
    )

    if scope == "redirect":
        await message.reply_text(REDIRECT)
        return

    if intent_result["intent"] == "greeting":
        previous_greeting = next(
            (
                item.get("content")
                for item in reversed(recent_for_scope)
                if item.get("role") == "assistant"
            ),
            None,
        )
        greeting = greeting_for_language(
            profile.get("preferred_language"),
            profile.get("display_name"),
            previous_greeting,
        )
        await db.save_message(user.id, "user", message.text)
        await db.save_message(user.id, "assistant", greeting)
        await message.reply_text(greeting)
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

        live_result = None
        is_live_request = intent_result["intent"] == "live_news" or research.needs_live_search(normalized_text)
        if is_live_request:
            live_result = await research.google_grounded_answer(
                normalized_text, profile.get("preferred_language")
            )
            if live_result is None:
                log.info("Live search primary unavailable; trying configured sequential search fallback chain")
                live_result = await research.search_fallback_answer(
                    normalized_text, profile.get("preferred_language")
                )
            if live_result is None:
                # Fail closed: never answer a current-news request from stale model memory.
                await message.reply_text(
                    "I couldn’t verify the latest anime information from current sources right now. "
                    "Please try again shortly."
                )
                return

        metadata = None
        title = None
        if not live_result:
            title = research.extract_title(normalized_text)
            if title:
                metadata = await research.anime_metadata(title)
                if metadata is None:
                    await message.reply_text(REDIRECT)
                    return

        usage = {}
        research_usage = {}
        if live_result:
            # Every live-search provider now feeds the same conversation writer.
            research_usage = dict(live_result.get("usage") or {})
            if research_usage:
                research_usage["operation"] = "grounded_research"
                research_usage["estimated_cost_usd"] = (
                    context.application.bot_data["ai"].estimate_cost_usd(
                        "gemini", research_usage, research_usage.get("model")
                    )
                )
            ai_history = [dict(item) for item in history]
            for history_index in range(len(ai_history) - 1, -1, -1):
                if ai_history[history_index].get("role") == "user":
                    ai_history[history_index]["content"] = normalized_text
                    break
            answer, provider, usage = await context.application.bot_data["ai"].reply(
                ai_history,
                profile.get("preferred_language"),
                memory_summary=summary_text,
                research_context=research.evidence_context(live_result),
                intent_context=(
                    f"Detected intent: {intent_result['intent']}. "
                    "This is a current anime research request. Answer from the supplied evidence only. "
                    + (
                        "BIG THREE RESPONSE FORMAT: Cover One Piece, Naruto/Boruto, and Bleach separately. "
                        "Give one short, useful, recent update for each franchise only when the supplied evidence supports it. "
                        "If no reliable recent update is present for a franchise, say you could not verify a notable update for it; do not invent one. "
                        "Talk like an anime fan chatting with a friend, not a news article. Use natural English or the user's selected language, "
                        "a few fitting emojis, and concise explanations. Never pad with unrelated gaming, store, or general entertainment news. "
                        if re.search(r"\bbig\s*3\b|big three", normalized_text, re.I) else ""
                    )
                    + f"User query: {normalized_text}"
                ),
                provider_order=(
                    ["groq", "openrouter", "gemini"]
                    if live_result.get("provider") == "tavily"
                    else None
                ),
            )
            fact_check = validate_generated_answer(answer, live_result)
            if not fact_check["ok"]:
                log.warning(
                    "Research answer rejected by fact verifier (unsupported_chapters=%s unsupported_dates=%s unsupported_confirmation=%s conflicted_chapters=%s)",
                    fact_check["unsupported_chapters"],
                    fact_check["unsupported_dates"],
                    fact_check["unsupported_confirmation"],
                    fact_check["conflicted_chapters"],
                )
                answer = verification_fallback(
                    profile.get("preferred_language"), fact_check
                )
        else:
            # Use corrected wording for understanding while preserving original transcript.
            ai_history = [dict(item) for item in history]
            for history_index in range(len(ai_history) - 1, -1, -1):
                if ai_history[history_index].get("role") == "user":
                    ai_history[history_index]["content"] = normalized_text
                    break
            answer, provider, usage = await context.application.bot_data["ai"].reply(
                ai_history, profile.get("preferred_language"),
                memory_summary=summary_text,
                research_context=research.context_for(metadata),
                intent_context=(
                    f"Detected intent: {intent_result['intent']}. "
                    f"Corrected query (only obvious typos): {normalized_text}"
                ),
            )

        if usage:
            usage = dict(usage)
            usage["operation"] = "response_generation"

        await db.save_message(user.id, "assistant", answer)
        log.info(
            "AI reply completed provider=%s input_tokens=%s output_tokens=%s total_tokens=%s",
            provider,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
        )

        for usage_provider, usage_record in (
            (live_result.get("provider") if live_result else None, research_usage),
            (provider, usage),
        ):
            if usage_record:
                try:
                    await db.log_ai_usage(user.id, usage_provider or provider, usage_record, usage_record.get("latency_ms"))
                except Exception as usage_exc:
                    # Telemetry must never make a successful user-facing answer fail.
                    log.warning("AI usage persistence skipped (%s)", type(usage_exc).__name__)

        if metadata and metadata.get("cover"):
            try:
                await message.reply_photo(photo=metadata["cover"], caption=f"🎌 {metadata['title']}")
            except Exception as exc:
                log.warning("Telegram anime cover send failed (%s)", type(exc).__name__)

        await send_formatted_answer(message, answer)
        if live_result and live_result.get("citations"):
            # Keep references available without turning the reply into a bibliography.
            source_links = []
            for source in live_result["citations"][:3]:
                url = html.escape(source["url"], quote=True)
                title = html.escape(source["title"][:65])
                source_links.append(f'<a href="{url}">{title}</a>')
            await message.reply_text(
                "🔎 <b>Sources:</b> " + " · ".join(source_links),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

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
    telegram_app.bot_data["research"] = AnimeResearchService(settings.gemini_api_key, settings.gemini_model, settings.tavily_api_key, settings.decodo_api_key, settings.langsearch_api_key, settings.search_order, settings.decodo_geo)

    # Commands
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("aiusage", ai_usage_command))
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

    # Route uncaught handler errors back to the webhook delivery outcome.
    telegram_app.add_error_handler(telegram_error_handler)

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

    if not secret or not secrets.compare_digest(secret, settings.webhook_secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content length")
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="Invalid content length")
        if declared_length > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Payload too large")

    try:
        # Stream and cap the body while reading. Checking request.body() after
        # buffering would still allow an oversized chunked request to consume memory.
        body_chunks = []
        body_size = 0
        async for chunk in request.stream():
            body_size += len(chunk)
            if body_size > MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Payload too large")
            body_chunks.append(chunk)
        raw_body = b"".join(body_chunks)
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("Telegram update must be a JSON object")
        telegram_app = request.app.state.telegram_app
        update = Update.de_json(payload, telegram_app.bot)
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Webhook payload rejected (%s)", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid update")

    if update is None or update.update_id is None:
        raise HTTPException(status_code=400, detail="Invalid update")

    db = request.app.state.db
    try:
        claim_token = await db.claim_telegram_update(update.update_id)
    except Exception as exc:
        log.error("Webhook idempotency storage unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Temporarily unavailable")

    if claim_token is None:
        log.info("Duplicate Telegram update ignored (update_id=%s)", update.update_id)
        return {"ok": True, "duplicate": True}

    try:
        failed_update_ids = telegram_app.bot_data.setdefault("failed_update_ids", set())
        failed_update_ids.discard(update.update_id)
        # The processing timeout is far shorter than the 10-minute database lease.
        # This prevents a live worker from outlasting its claim and being reclaimed.
        await asyncio.wait_for(
            telegram_app.process_update(update),
            timeout=WEBHOOK_PROCESSING_TIMEOUT_SECONDS,
        )

        # PTB routes callback exceptions through process_error() instead of
        # re-raising them from process_update(). Check the registered error hook
        # before acknowledging the webhook so Telegram can retry failed updates.
        failed_update_ids = telegram_app.bot_data.setdefault("failed_update_ids", set())
        if update.update_id in failed_update_ids:
            failed_update_ids.discard(update.update_id)
            await db.fail_telegram_update(
                update.update_id,
                claim_token,
                "handler_error",
            )
            raise HTTPException(status_code=500, detail="Update processing failed")

        await db.complete_telegram_update(update.update_id, claim_token)
    except HTTPException:
        raise
    except Exception as exc:
        try:
            await db.fail_telegram_update(
                update.update_id,
                claim_token,
                f"dispatch_{type(exc).__name__}",
            )
        except Exception as storage_exc:
            log.error("Could not release failed update claim (%s)", type(storage_exc).__name__)

        log.warning("Webhook update processing failed (type=%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Update processing failed")

    return {"ok": True}
