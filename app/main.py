import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from app.config import get_settings
from app.db import Database
from app.handlers import start, legal_callback, consent_callback, language_callback, settings_command, newchat_command, newchat_callback, privacy_command, delete_data_command, delete_data_callback
from app.ai.router import AIRouter
settings=get_settings()
logging.basicConfig(level=getattr(logging,settings.log_level.upper(),logging.INFO))
log=logging.getLogger(__name__)

async def chat_message(update: Update, context):
    message=update.effective_message; user=update.effective_user
    if not message or not message.text or not user: return
    db=context.application.bot_data["db"]; profile=await db.get_profile(user.id)
    if not profile or not profile.get("consented_at"):
        await message.reply_text("Please use /start and review the consent information first."); return
    await db.save_message(user.id,"user",message.text)
    history=await db.get_recent_messages(user.id)
    try:
        answer,provider=await context.application.bot_data["ai"].reply(history,profile.get("preferred_language"))
        await db.save_message(user.id,"assistant",answer)
        log.info("AI reply completed via provider=%s",provider)
        for i in range(0,len(answer),4000): await message.reply_text(answer[i:i+4000])
    except Exception as exc:
        log.warning("AI response failed (%s)",type(exc).__name__)
        await message.reply_text("I'm having trouble reaching my AI providers right now. Please try again shortly.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    db=Database(settings); await db.connect()
    telegram_app=Application.builder().token(settings.telegram_bot_token).build()
    telegram_app.bot_data["db"]=db; telegram_app.bot_data["ai"]=AIRouter(settings)
    telegram_app.add_handler(CommandHandler("start",start)); telegram_app.add_handler(CommandHandler("settings",settings_command))
    telegram_app.add_handler(CommandHandler("newchat",newchat_command)); telegram_app.add_handler(CommandHandler("privacy",privacy_command))
    telegram_app.add_handler(CommandHandler("delete_my_data",delete_data_command))
    telegram_app.add_handler(CallbackQueryHandler(legal_callback,pattern=r"^legal:")); telegram_app.add_handler(CallbackQueryHandler(consent_callback,pattern=r"^consent:"))
    telegram_app.add_handler(CallbackQueryHandler(language_callback,pattern=r"^lang:")); telegram_app.add_handler(CallbackQueryHandler(newchat_callback,pattern=r"^newchat:"))
    telegram_app.add_handler(CallbackQueryHandler(delete_data_callback,pattern=r"^delete_data:")); telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,chat_message))
    await telegram_app.initialize(); await telegram_app.start()
    app.state.db=db; app.state.telegram_app=telegram_app
    try: yield
    finally:
        await telegram_app.stop(); await telegram_app.shutdown(); await db.close()

app=FastAPI(title="Ani Zeo",lifespan=lifespan)
@app.get("/")
async def health(): return {"status":"ok","service":"ani-zeo"}
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret=request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret or secret!=settings.webhook_secret: raise HTTPException(status_code=403,detail="Forbidden")
    try:
        payload=await request.json(); telegram_app=request.app.state.telegram_app
        update=Update.de_json(payload,telegram_app.bot); await telegram_app.process_update(update)
    except Exception as exc:
        log.warning("Webhook update failed (%s)",type(exc).__name__); raise HTTPException(status_code=400,detail="Invalid update")
    return {"ok":True}
