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

import asyncio
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
        logger.warning(
            f"Unauthorized /help command from user {update.effective_user.id}"
        )
        await update.message.reply_text("Unauthorized")
        return

    help_text = """
Cat AI Factory - Telegram Bridge (Ingress-only)

Available commands:
- /help: Show this message.
- /status <job_id>: Check the status of a job.
- Any other message will be written to the inbox for processing.

Note: This is an ingress-only bridge. It does not execute commands directly.
    """
    await update.message.reply_text(help_text.strip())


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the status of a specific job."""
    if not is_authorized(update.effective_user.id):
        logger.warning(
            f"Unauthorized /status command from user {update.effective_user.id}"
        )
        await update.message.reply_text("Unauthorized")
        return

    if not context.args:
        await update.message.reply_text("Usage: /status <job_id>")
        return

    job_id = context.args[0]
    state_file = LOGS_PATH / job_id / "state.json"

    logger.info(f"Status request for job '{job_id}' from user {update.effective_user.id}. Reading {state_file}")

    if not state_file.is_file():
        await update.message.reply_text(f"Job not found: {job_id}")
        return

    try:
        with open(state_file, "r") as f:
            state_data = json.load(f)

        # Format a user-friendly reply
        reply = [f"Status for job: {state_data.get('job_id', job_id)}"]
        if "state" in state_data:
            reply.append(f"State: {state_data['state']}")
        if "status" in state_data: # Alternative key
            reply.append(f"Status: {state_data['status']}")
        if "last_updated" in state_data:
            reply.append(f"Last Updated: {state_data['last_updated']}")
        if "progress" in state_data:
            summary = state_data["progress"].get("summary", "No summary.")
            reply.append(f"Progress: {summary}")

        await update.message.reply_text("\n".join(reply))

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in state file: {state_file}")
        await update.message.reply_text(f"Error: State file for {job_id} is corrupted.")
    except Exception as e:
        logger.error(f"Failed to read state file {state_file}: {e}")
        await update.message.reply_text("An internal error occurred.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles generic messages, writing them to the inbox."""
    if not is_authorized(update.effective_user.id):
        logger.warning(
            f"Unauthorized message from user {update.effective_user.id}. Ignoring."
        )
        # Optional: notify unauthorized user. Avoid giving too much info.
        # await update.message.reply_text("Unauthorized")
        return

    message = update.message
    text = message.text
    command, args = (None, None)

    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else None

    # Construct the JSON artifact
    artifact = {
        "source": "telegram",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "update_id": update.update_id,
        "chat_id": message.chat_id,
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "text": text,
        "command": command,
        "args": args,
    }

    # Generate a unique and stable filename
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    filename = f"telegram-{update.update_id}-{ts}.json"
    filepath = INBOX_PATH / filename

    try:
        INBOX_PATH.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(artifact, f, indent=2)
        logger.info(f"Wrote message artifact to {filepath}")
        await message.reply_text("OK: Message received by inbox.")

    except Exception as e:
        logger.error(f"Failed to write message artifact to {filepath}: {e}")
        await message.reply_text("Error: Could not write to inbox.")


def main() -> None:
    """Starts the Telegram bot."""
    logger.info("Starting Telegram bridge...")

    # Ensure sandbox directories exist
    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    logger.info(f"Sandbox root: {SANDBOX_PATH}")
    logger.info(f"Watching for logs in: {LOGS_PATH}")
    logger.info(f"Writing ingress messages to: {INBOX_PATH}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    # Handle all other text messages that are not commands handled above
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bridge started. Polling for updates...")
    app.run_polling()


if __name__ == "__main__":
    main()