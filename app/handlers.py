from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from html import escape
from app.config import get_settings
LANGUAGES = [("🇮🇳 Tenglish", "tenglish"), ("🇮🇳 Hinglish", "hinglish"), ("🇮🇳 Tanglish", "tanglish"), ("🇬🇧 English", "english")]
TERMS_VERSION = "v1"

def language_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"lang:{code}")] for label, code in LANGUAGES])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; db = context.application.bot_data["db"]
    await db.ensure_profile(user.id, user.username, user.full_name)
    profile = await db.get_profile(user.id)
    if profile and profile.get("consented_at"):
        await update.effective_message.reply_text("Welcome back! I'm Ani Zeo 🎌 Your anime companion. Ask me anything about anime or describe what you're looking for.")
        return
    keyboard = InlineKeyboardMarkup([
      [InlineKeyboardButton("📜 Terms & Conditions", callback_data="legal:terms")],
      [InlineKeyboardButton("🔒 Privacy Notice", callback_data="legal:privacy")],
      [InlineKeyboardButton("🤖 AI Disclaimer", callback_data="legal:ai")],
      [InlineKeyboardButton("✅ I agree & continue", callback_data="consent:yes"), InlineKeyboardButton("❌ Not now", callback_data="consent:no")]])
    await update.effective_message.reply_text("Yo! I'm Ani Zeo 🎌 — your AI anime companion. Review the information below before continuing.", reply_markup=keyboard)

async def legal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    docs={
      "legal:terms":("Terms & Conditions","Ani Zeo is an entertainment companion. Use it lawfully and respectfully. AI responses may be wrong; availability and recommendations can change. Respect third-party rights. Service features and availability may change."),
      "legal:privacy":("Privacy Notice","The bot stores your Telegram user ID, basic profile details, language, consent status and saved conversation messages in its configured database. Messages sent to AI providers are processed by those providers to generate replies. Avoid sharing secrets or sensitive personal data. Provider policies also apply."),
      "legal:ai":("AI Disclaimer","AI can misunderstand you or provide incorrect or outdated information. Recommendation fit is an estimate. Verify important facts and official release announcements.")}
    title,body=docs[q.data]; await q.message.reply_text(f"{title}\n\n{body}")

async def consent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); db=context.application.bot_data["db"]
    if q.data=="consent:no":
        await q.edit_message_text("No problem. I won't continue onboarding. Use /start if you want to review it later."); return
    await db.set_consent(update.effective_user.id, TERMS_VERSION)
    await q.edit_message_text("Thanks! Choose your preferred language next.")
    await q.message.reply_text("Choose a language:", reply_markup=language_keyboard())

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); language=q.data.split(":",1)[1]
    if language not in {v for _,v in LANGUAGES}:
        await q.message.reply_text("That language choice isn't available."); return
    await context.application.bot_data["db"].set_language(update.effective_user.id, language)
    await q.edit_message_text(f"Language saved: {language.title()} ✅")
    await q.message.reply_text("Nice! 🎌 Tell me your favourite anime or genres whenever you like, or start chatting now.\n\nTry: Recommend anime like Dr. Stone with science and kingdom building.")

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
