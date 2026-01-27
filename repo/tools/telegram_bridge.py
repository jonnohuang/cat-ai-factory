import os, time, pathlib, json, datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

INBOX = pathlib.Path("/sandbox/inbox")
OUTBOX = pathlib.Path("/sandbox/outbox")

def now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    INBOX.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(parents=True, exist_ok=True)

    chat_id = update.effective_chat.id if update.effective_chat else None
    text = update.message.text if update.message else ""

    payload = {
        "ts": now_stamp(),
        "chat_id": chat_id,
        "text": text
    }
    fname = f"{payload['ts']}-chat{chat_id}.json"
    (INBOX / fname).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Simple UX: acknowledge + if outbox/latest.txt exists, send it back
    await update.message.reply_text("✅ Received. I wrote your message to /sandbox/inbox/")

    latest = OUTBOX / "latest.txt"
    if latest.exists():
        msg = latest.read_text(encoding="utf-8")[:3500]
        await update.message.reply_text(msg)

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or "PASTE_YOUR_TOKEN_HERE" in token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env before running.")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
