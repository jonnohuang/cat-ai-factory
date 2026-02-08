# repo/tools/telegram_bridge.py
"""
Cat AI Factory - Telegram Bridge (Ingress-only)

This tool acts as a secure bridge between Telegram and the file-based bus.
It performs two primary functions:
1. INGRESS: Listens for messages from an authorized user, validates them,
   and writes them as structured JSON artifacts to /sandbox/inbox/.
2. STATUS: Provides a read-only /status <job_id> command to check the
   state of a job by reading its state.json artifact.

Design Invariants:
- This bridge is an ADAPTER only. It does not contain planner or orchestrator logic.
- It communicates strictly via the filesystem bus (/sandbox/inbox, /sandbox/logs).
- It has no authority to execute, modify, or delete artifacts outside its scope.
- All secrets are handled via environment variables and are never logged or exposed.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- Configuration ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

SANDBOX_PATH = Path(os.getenv("CAF_SANDBOX_PATH", "sandbox")).resolve()
INBOX_PATH = SANDBOX_PATH / "inbox"
LOGS_PATH = SANDBOX_PATH / "logs"

# --- Security: Load secrets from environment ---
try:
    TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
except (KeyError, ValueError) as e:
    logger.critical(f"CRITICAL: Missing or invalid environment variable: {e}")
    logger.critical(
        "Please set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID."
    )
    exit(1)


def is_authorized(user_id: int) -> bool:
    """Checks if the user is authorized."""
    return user_id == TELEGRAM_ALLOWED_USER_ID


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a short help message."""
    if not is_authorized(update.effective_user.id):
        return
    help_text = """
Cat AI Factory - Telegram Bridge (Ingress-only)

Available commands:
- /help: Show this message.
- /status <job_id>: Check the status of a job.
- /plan <prompt>: Submit a new video plan.
- /approve <job_id>: Approve a job for YouTube publishing.
- /reject <job_id> [reason]: Reject a job.
- Any other message will be written to the inbox for processing.
    """
    await update.message.reply_text(help_text.strip())


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the status of a specific job."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized")
        return

    if not context.args:
        await update.message.reply_text("Usage: /status <job_id>")
        return

    job_id = context.args[0]
    state_file = LOGS_PATH / job_id / "state.json"
    logger.info(f"Status request for job '{job_id}'. Reading {state_file}")

    if not state_file.is_file():
        await update.message.reply_text(f"Job not found: {job_id}")
        return

    try:
        with open(state_file, "r") as f:
            state_data = json.load(f)
        reply = [f"Status for job: {state_data.get('job_id', job_id)}"]
        if "status" in state_data:
            reply.append(f"Status: {state_data['status']}")
        await update.message.reply_text("\n".join(reply))
    except Exception as e:
        logger.error(f"Failed to read state file {state_file}: {e}")
        await update.message.reply_text("An internal error occurred.")


async def _write_artifact(filepath: Path, data: dict):
    """Helper to write a JSON artifact to the inbox."""
    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Wrote artifact to {filepath}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles generic messages and special commands."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized message from user {user_id}. Ignoring.")
        return

    message = update.message
    text = message.text.strip()
    update_id = update.update_id
    was_special_command = True # Assume true, set to false for generic messages

    try:
        if text.startswith("/plan "):
            prompt = text[len("/plan "):].strip()
            if not prompt:
                await message.reply_text("Usage: /plan <prompt>")
                return
            artifact = {
                "source": "telegram", "prompt": prompt,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
            await _write_artifact(INBOX_PATH / f"plan-{update_id}.json", artifact)
            await message.reply_text("✅ Instruction logged to inbox: plan")

        elif text.startswith("/approve "):
            parts = text.split()
            if len(parts) < 2:
                await message.reply_text("Usage: /approve <job_id>")
                return
            job_id = parts[1]
            artifact = {
                "source": "telegram", "job_id": job_id, "platform": "youtube",
                "approved": True, "approved_by": f"telegram:{user_id}",
                "approved_at": datetime.now(timezone.utc).isoformat(), "nonce": update_id,
            }
            await _write_artifact(INBOX_PATH / f"approve-{job_id}-youtube-{update_id}.json", artifact)
            await message.reply_text("✅ Instruction logged to inbox: approve")

        elif text.startswith("/reject "):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                await message.reply_text("Usage: /reject <job_id> [reason]")
                return
            job_id = parts[1]
            reason = parts[2] if len(parts) > 2 else ""
            artifact = {
                "source": "telegram", "job_id": job_id, "approved": False,
                "reason": reason, "rejected_by": f"telegram:{user_id}",
                "rejected_at": datetime.now(timezone.utc).isoformat(), "nonce": update_id,
            }
            await _write_artifact(INBOX_PATH / f"reject-{job_id}-{update_id}.json", artifact)
            await message.reply_text("✅ Instruction logged to inbox: reject")
        
        else:
            was_special_command = False

    except Exception as e:
        logger.error(f"Failed during special command processing: {e}")
        await message.reply_text("Error processing command.")
        # Do not proceed to raw artifact writing on a partial failure
        return

    # --- Always write the raw message artifact ---
    raw_artifact = {
        "source": "telegram", "received_at": datetime.now(timezone.utc).isoformat(),
        "update_id": update_id, "chat_id": message.chat_id, "user_id": user_id,
        "username": message.from_user.username, "text": text,
    }
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    raw_filepath = INBOX_PATH / f"telegram-{update_id}-{ts}.json"
    
    try:
        await _write_artifact(raw_filepath, raw_artifact)
        if not was_special_command:
            await message.reply_text("OK: Message received by inbox.")
    except Exception as e:
        logger.error(f"Failed to write raw message artifact to {raw_filepath}: {e}")
        if not was_special_command:
            await message.reply_text("Error: Could not write message to inbox.")


def main() -> None:
    """Starts the Telegram bot."""
    logger.info("Starting Telegram bridge...")
    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    logger.info(f"Sandbox root: {SANDBOX_PATH}")
    logger.info(f"Writing ingress messages to: {INBOX_PATH}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register CommandHandlers first for specific commands like /help and /status.
    # These will be matched before the generic MessageHandler.
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # **FIX:** Use a MessageHandler for ALL text to ensure commands like /plan
    # are processed in our custom logic, allowing multiple artifacts to be created.
    # CommandHandlers for /help and /status will catch those first.
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    
    logger.info("Telegram bridge started. Polling for updates...")
    app.run_polling()


if __name__ == "__main__":
    main()