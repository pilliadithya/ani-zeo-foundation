from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from html import escape
import random
from app.config import get_settings
LANGUAGES = [("Tenglish", "tenglish"), ("Hinglish", "hinglish"), ("Tanglish", "tanglish"), ("English", "english")]
TERMS_VERSION = "v1"


def normalise_display_name(value: str) -> str | None:
    """Validate a short user-chosen display name without restricting its script."""
    cleaned = " ".join("".join(char for char in str(value) if char.isprintable()).split())
    if not cleaned or len(cleaned) > 40:
        return None
    return cleaned


async def handle_onboarding_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Consume a text message as the requested display name during onboarding."""
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return False
    db = context.application.bot_data["db"]
    profile = await db.get_profile(user.id) or {}
    if profile.get("onboarding_step") != "awaiting_name":
        return False
    display_name = normalise_display_name(message.text)
    if not display_name:
        await message.reply_text("Please send a name between 1 and 40 characters. You can use the script you prefer.")
        return True
    await db.set_display_name(user.id, display_name)
    await db.set_onboarding_step(user.id, "awaiting_language")
    await message.reply_text(
        f"Nice to meet you, {display_name}! ✨\n\nChoose the language you'd like Ani Zeo to use:",
        reply_markup=language_keyboard(),
    )
    return True

def language_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"lang:{code}")] for label, code in LANGUAGES])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the compact welcome/disclaimer and resume any interrupted onboarding."""
    user = update.effective_user
    if not user:
        return
    db = context.application.bot_data["db"]
    await db.ensure_profile(user.id, user.username, None)
    profile = await db.get_profile(user.id) or {}
    step = profile.get("onboarding_step") or "welcome"
    if profile.get("consented_at") and profile.get("preferred_language") and step == "completed":
        name = profile.get("display_name") or user.first_name or "nakama"
        await update.effective_message.reply_text(f"Welcome back, {name}! ✨ Ready for another anime adventure?")
        return
    if profile.get("consented_at") and step == "awaiting_name":
        await update.effective_message.reply_text("Nice to have you here! 😄 What name should I call you?")
        return
    if profile.get("consented_at") and step == "awaiting_language":
        await update.effective_message.reply_text("Choose the language you'd like Ani Zeo to use:", reply_markup=language_keyboard())
        return
    welcome = (
        "✨ <b>Welcome to ANI ZEO!</b>\n"
        "<i>Your Anime Discovery Companion</i>\n\n"
        "Hey, anime nakama! 👋 Discover anime and manga, explore characters and watch orders, and find useful anime updates with your companion.\n\n"
        "💡 <b>Did you know?</b> Ani Zeo is an independent prototype created by <b>Anime Monarch</b> and is currently under development and testing.\n\n"
        "⚠️ <b>AI notice:</b> AI-generated answers can be inaccurate or outdated. Check important announcements and release details against official sources.\n\n"
        "🔒 <b>Privacy:</b> Telegram provides your account ID automatically. We ask only for the name you'd like us to use and your preferred language. Your profile and conversation messages may be stored to operate the service; messages sent to AI providers are processed to generate replies. Avoid sharing passwords or sensitive information. Use /privacy to learn about data deletion.\n\n"
        "Ani Zeo is an independent project and is not affiliated with anime studios, publishers or streaming platforms.\n\n"
        "Ready to begin?"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✨ Continue", callback_data="consent:yes")], [InlineKeyboardButton("Not now", callback_data="consent:no")]])
    await update.effective_message.reply_text(welcome, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def legal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    docs={
      "legal:terms":("Terms & Conditions","Ani Zeo is an entertainment companion. Use it lawfully and respectfully. AI responses may be wrong; availability and recommendations can change. Respect third-party rights. Service features and availability may change."),
      "legal:privacy":("Privacy Notice","The bot stores your Telegram user ID, basic profile details, language, consent status and saved conversation messages in its configured database. Messages sent to AI providers are processed by those providers to generate replies. Avoid sharing secrets or sensitive personal data. Provider policies also apply."),
      "legal:ai":("AI Disclaimer","AI can misunderstand you or provide incorrect or outdated information. Recommendation fit is an estimate. Verify important facts and official release announcements.")}
    title,body=docs[q.data]; await q.message.reply_text(f"{title}\n\n{body}")

async def consent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    db = context.application.bot_data["db"]
    if q.data == "consent:no":
        await db.set_onboarding_step(update.effective_user.id, "declined")
        await q.edit_message_text("No problem. Ani Zeo won't continue onboarding. You can send /start whenever you'd like to review the welcome note again.")
        return
    await db.set_consent(update.effective_user.id, TERMS_VERSION)
    await db.set_onboarding_step(update.effective_user.id, "awaiting_name")
    await q.edit_message_text("Adventure accepted! ✨\n\nWhat name should I call you?")


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    language = q.data.split(":", 1)[1]
    if language not in {value for _, value in LANGUAGES}:
        await q.message.reply_text("That language choice isn't available.")
        return
    db = context.application.bot_data["db"]
    await db.set_language(update.effective_user.id, language)
    await db.set_onboarding_step(update.effective_user.id, "completed")
    greetings = {
        "english": ["Heyyy! 👋 Your anime adventure starts now. What shall we explore?", "Welcome aboard, nakama! ✨ Ready to discover something amazing?", "A new chapter begins! 📖 What anime are we diving into today?"],
        "tenglish": ["Hey bro! 😎 Eeroju ye anime gurinchi explore cheddham?", "Mana anime adventure start ayyindi! ⚔️ Em discover cheddham?", "Welcome, nakama! ✨ Nee next favourite anime ni kanipedadham!"],
        "hinglish": ["Yo bro! 😎 Aaj kis anime ki duniya explore karein?", "Nayi anime adventure shuru! ⚔️ Kya discover karna hai?", "Welcome, nakama! ✨ Tumhara next favourite anime dhoondhein?"],
        "tanglish": ["Vanakkam, nakama! ✨ Innaiku endha anime explore pannalaam?", "Pudhu anime adventure start pannalaama? ⚔️", "Hey bro! 😎 Un next favourite anime-a kandupidikkalaam!"],
    }
    greeting = random.choice(greetings[language])
    await q.edit_message_text(f"Language saved: {language.title()} ✅")
    await q.message.reply_text(greeting)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile=await context.application.bot_data["db"].get_profile(update.effective_user.id)
    if not profile or not profile.get("consented_at"):
        await update.effective_message.reply_text("Please use /start and review the consent information first."); return
    await update.effective_message.reply_text("Choose your preferred language:", reply_markup=language_keyboard())

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Start fresh",callback_data="newchat:yes"),InlineKeyboardButton("Cancel",callback_data="newchat:no")]])
    await update.effective_message.reply_text("Start a fresh conversation? Your saved preferences will remain. This clears saved bot context, not Telegram messages.", reply_markup=keyboard)

async def newchat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="newchat:no": await q.edit_message_text("Cancelled — we'll continue where we left off."); return
    await context.application.bot_data["db"].clear_conversation(update.effective_user.id)
    await q.edit_message_text("Fresh start! 🎌 Your saved preferences remain. What anime are we talking about?")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Use /delete_my_data to request deletion of your stored profile and saved conversation history. This does not delete Telegram messages or data already processed by external providers.")

async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("Delete my stored data",callback_data="delete_data:yes"),InlineKeyboardButton("Cancel",callback_data="delete_data:no")]])
    await update.effective_message.reply_text("This permanently deletes your stored profile, preferences and saved conversation history. It cannot delete Telegram messages or data already processed by external providers. Continue?", reply_markup=keyboard)

async def delete_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="delete_data:no": await q.edit_message_text("Cancelled. Your stored data is unchanged."); return
    await context.application.bot_data["db"].delete_user_data(update.effective_user.id)
    await q.edit_message_text("Your stored Ani Zeo data has been deleted. Send /start if you'd like to begin again.")


async def ai_usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show aggregate AI token usage to explicitly configured Telegram admins only."""
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    configured = get_settings().ai_usage_admin_ids
    allowed_ids = {
        int(value.strip())
        for value in configured.split(",")
        if value.strip().isdigit()
    }
    if not allowed_ids or user.id not in allowed_ids:
        await message.reply_text("This admin-only usage report is not enabled for this account.")
        return

    db = context.application.bot_data["db"]
    rows = await db.get_ai_usage_summary(days=7)
    if not rows:
        await message.reply_text("No AI usage records are available for the last 7 days yet.")
        return

    lines = ["<b>🤖 Ani Zeo · AI usage (last 7 days)</b>"]
    for row in rows:
        provider = escape(str(row["provider"] or "unknown"))
        operation = escape(str(row["operation"] or "chat_response"))
        requests = int(row["requests"] or 0)
        input_tokens = row["input_tokens"]
        output_tokens = row["output_tokens"]
        total_tokens = row["total_tokens"]
        cost = row["estimated_cost_usd"]
        lines.append(
            f"\n<b>{provider}</b> · {operation}"
            f"\nRequests: {requests}"
            f"\nInput: {input_tokens if input_tokens is not None else 'n/a'}"
            f" · Output: {output_tokens if output_tokens is not None else 'n/a'}"
            f" · Total: {total_tokens if total_tokens is not None else 'n/a'}"
        )
        if cost is not None:
            lines.append("\nEstimated cost: " + format(float(cost), ".6f") + " USD")
    lines.append("\n<i>Provider-reported token counts are authoritative. Estimates and unavailable fields are labelled separately.</i>")
    await message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
