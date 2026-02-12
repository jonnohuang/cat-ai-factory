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
- MUST NOT overwrite existing inbox artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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
ASSETS_PATH = SANDBOX_PATH / "assets"
DIST_ARTIFACTS_PATH = SANDBOX_PATH / "dist_artifacts"

# --- Security: Load secrets from environment ---
try:
    TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
except (KeyError, ValueError) as e:
    logger.critical(f"CRITICAL: Missing or invalid environment variable: {e}")
    logger.critical("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID.")
    raise SystemExit(1)


def is_authorized(user_id: int) -> bool:
    """Checks if the user is authorized."""
    return user_id == TELEGRAM_ALLOWED_USER_ID


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_manifest() -> Tuple[Optional[dict], Optional[str]]:
    manifest_path = ASSETS_PATH / "manifest.json"
    if not manifest_path.is_file():
        return None, "manifest.json not found at sandbox/assets/manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError:
        return None, "manifest.json is invalid JSON"
    except Exception as e:
        return None, f"Error reading manifest.json: {e}"


def _parse_creativity_tokens(prompt: str) -> Tuple[str, Optional[Dict[str, str]]]:
    """
    Best-effort parsing of optional creativity tokens anywhere in a prompt.

    Supported tokens (case-insensitive keys):
      - creativity=canon|balanced|experimental
      - canon_fidelity=high|medium

    Returns:
      (cleaned_prompt, creativity_dict_or_None)
    """
    allowed_mode = {"canon", "balanced", "experimental"}
    allowed_fidelity = {"high", "medium"}

    tokens = prompt.split()
    kept: list[str] = []
    creativity: Dict[str, str] = {}

    for tok in tokens:
        if "=" not in tok:
            kept.append(tok)
            continue

        key, value = tok.split("=", 1)
        key_l = key.strip().lower()
        value_l = value.strip().lower()

        if key_l in {"creativity", "mode"}:
            if value_l in allowed_mode:
                creativity["mode"] = value_l
            else:
                kept.append(tok)
        elif key_l == "canon_fidelity":
            if value_l in allowed_fidelity:
                creativity["canon_fidelity"] = value_l
            else:
                kept.append(tok)
        else:
            kept.append(tok)

    cleaned = " ".join(kept).strip()
    return cleaned, (creativity if creativity else None)


async def raw_update_logger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Always log raw text updates for authorized users."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return

    text = update.message.text.strip()
    update_id = update.update_id
    raw_artifact = {
        "source": "telegram",
        "received_at": _utc_now_z(),
        "update_id": update_id,
        "chat_id": update.message.chat_id,
        "user_id": user_id,
        "username": update.message.from_user.username,
        "text": text,
    }
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    raw_filepath = INBOX_PATH / f"telegram-{update_id}-{ts}.json"

    try:
        await _write_artifact(raw_filepath, raw_artifact)
    except Exception as e:
        logger.error(f"Failed to write raw message artifact to {raw_filepath}: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message for /start."""
    if not is_authorized(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    welcome_text = """
🐾 Welcome to Cat AI Factory
You are the supervisor. Authorized users only.

I write control artifacts to: sandbox/inbox/
I can read status from: sandbox/logs/ and sandbox/dist_artifacts/

Try:
/help
    """.strip()
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the /help command menu."""
    if not is_authorized(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    help_text = """
🐾 CAF Telegram Bridge (authorized users only)

Commands:
/plan <prompt> [creativity=canon|balanced|experimental] [canon_fidelity=high|medium]
/daily [--auto-style|--human-style] <brief text...>
/approve <job_id>
/reject <job_id> [reason]
/style list
/style set <key>
/status <job_id> [platform]
/help

Daily plan:
Defaults: auto_style=true
A/B/C lanes: numbers are volume targets (how many videos/jobs), NOT time slots.
Example:
/daily --human-style A=1 B=0 C=2 theme: office cats, barista mishaps

Style workflow (optional):
1) /style list
2) /style set <key>
3) /daily ... or /plan ...

Note: commands write inbox artifacts only; this bridge does not run the factory.
    """.strip()
    await update.message.reply_text(help_text)


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /plan <prompt> with optional creativity tokens."""
    if not is_authorized(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    args = context.args or []
    prompt_raw = " ".join(args).strip()
    if not prompt_raw:
        await update.message.reply_text(
            "Usage: /plan <prompt> [creativity=canon|balanced|experimental] [canon_fidelity=high|medium]"
        )
        return

    cleaned_prompt, creativity = _parse_creativity_tokens(prompt_raw)

    update_id = update.update_id
    artifact: Dict[str, Any] = {
        "source": "telegram",
        "received_at": _utc_now_z(),
        "command": "plan",
        # Back-compat: keep the original field name as well as the clearer one.
        "prompt": cleaned_prompt,
        "brief_text": cleaned_prompt,
        "nonce": str(update_id),
    }
    if creativity:
        artifact["creativity"] = creativity

    filepath = INBOX_PATH / f"plan-{update_id}.json"
    await _write_artifact(filepath, artifact)
    await update.message.reply_text("✅ Instruction logged to inbox: plan")


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /daily [--auto-style|--human-style] <brief text...>."""
    if not is_authorized(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    args = context.args or []
    auto_style = True
    brief_args = args[:]

    if brief_args and brief_args[0] in ("--auto-style", "--human-style"):
        auto_style = brief_args[0] == "--auto-style"
        brief_args = brief_args[1:]

    brief_text = " ".join(brief_args).strip()
    if not brief_text:
        await update.message.reply_text(
            "Usage: /daily [--auto-style|--human-style] <brief text...>"
        )
        return

    today = datetime.now().date().isoformat()
    update_id = update.update_id
    artifact = {
        "source": "telegram",
        "received_at": _utc_now_z(),
        "command": "daily_plan",
        "date": today,
        "brief_text": brief_text,
        "auto_style": auto_style,
        "approved_by": f"telegram:{update.effective_user.id}",
        "nonce": str(update_id),
    }

    filepath = INBOX_PATH / f"daily-plan-{today}-{update_id}.json"
    await _write_artifact(filepath, artifact)
    await update.message.reply_text(
        f"✅ Daily plan captured for {today} (auto_style={str(auto_style).lower()})"
    )


async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /style list and /style set commands."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    command = context.args[0] if context.args else ""

    if command == "list":
        manifest, error = _read_manifest()
        if error:
            await update.message.reply_text(error)
            return

        keys = list(manifest.keys()) if isinstance(manifest, dict) else []
        if not keys:
            await update.message.reply_text("No styles found in manifest.json.")
            return

        max_keys = 20
        reply_lines = keys[:max_keys]
        if len(keys) > max_keys:
            reply_lines.append(f"... ({len(keys) - max_keys} more)")

        await update.message.reply_text("\n".join(reply_lines))

    elif command == "set":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /style set <key>")
            return

        style_key = context.args[1]
        manifest, error = _read_manifest()
        if error:
            await update.message.reply_text(error)
            return

        if not isinstance(manifest, dict) or style_key not in manifest:
            await update.message.reply_text("Invalid key. Use '/style list' to see available keys.")
            return

        update_id = update.update_id
        artifact = {
            "source": "telegram",
            "received_at": _utc_now_z(),
            "command": "style_set",
            "style_key": style_key,
            "style_notes": manifest.get(style_key, ""),
            "approved_by": f"telegram:{user_id}",
            "nonce": str(update_id),
        }

        filepath = INBOX_PATH / f"style-set-{update_id}.json"
        await _write_artifact(filepath, artifact)
        await update.message.reply_text(f"✅ Style set request written: {style_key}")

    else:
        await update.message.reply_text("Usage: /style <list|set> [key]")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /approve <job_id>."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /approve <job_id>")
        return

    job_id = context.args[0].strip()
    if not job_id:
        await update.message.reply_text("Usage: /approve <job_id>")
        return

    update_id = update.update_id
    artifact = {
        "source": "telegram",
        "job_id": job_id,
        "platform": "youtube",
        "approved": True,
        "approved_by": f"telegram:{user_id}",
        "approved_at": _utc_now_z(),
        "nonce": update_id,
    }
    await _write_artifact(
        INBOX_PATH / f"approve-{job_id}-youtube-{update_id}.json", artifact
    )
    await update.message.reply_text("✅ Instruction logged to inbox: approve")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /reject <job_id> [reason]."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /reject <job_id> [reason]")
        return

    job_id = context.args[0].strip()
    reason = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""

    update_id = update.update_id
    artifact = {
        "source": "telegram",
        "job_id": job_id,
        "approved": False,
        "reason": reason,
        "rejected_by": f"telegram:{user_id}",
        "rejected_at": _utc_now_z(),
        "nonce": update_id,
        "platform": "youtube",
    }
    await _write_artifact(
        INBOX_PATH / f"reject-{job_id}-youtube-{update_id}.json", artifact
    )
    await update.message.reply_text("✅ Instruction logged to inbox: reject")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the status of a specific job."""
    if not is_authorized(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /status <job_id> [platform]")
        return

    job_id = context.args[0]
    platform = context.args[1] if len(context.args) > 1 else "youtube"

    factory_status = "MISSING"
    publish_status = "MISSING"

    # Read factory state
    state_file = LOGS_PATH / job_id / "state.json"
    if state_file.is_file():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                factory_status = state_data.get("status", "UNKNOWN")
        except json.JSONDecodeError:
            factory_status = "INVALID JSON"
        except Exception as e:
            logger.error(f"Error reading factory state for {job_id}: {e}")
            factory_status = "ERROR"

    # Read publish state
    dist_state_file = DIST_ARTIFACTS_PATH / job_id / f"{platform}.state.json"
    if dist_state_file.is_file():
        try:
            with open(dist_state_file, "r", encoding="utf-8") as f:
                dist_state_data = json.load(f)
                publish_status = dist_state_data.get("status", "UNKNOWN")
        except json.JSONDecodeError:
            publish_status = "INVALID JSON"
        except Exception as e:
            logger.error(f"Error reading publish state for {job_id} on {platform}: {e}")
            publish_status = "ERROR"

    reply = f"📦 Job: {job_id}\nFactory: {factory_status}\nPublish({platform}): {publish_status}"
    await update.message.reply_text(reply)


async def _write_artifact(filepath: Path, data: dict) -> None:
    """
    Helper to write a JSON artifact to the inbox.

    Invariants:
    - Create parent dirs if needed
    - MUST NOT overwrite an existing file
    - Atomic write
    """
    INBOX_PATH.mkdir(parents=True, exist_ok=True)

    # Do not overwrite
    if filepath.exists():
        raise FileExistsError(f"Refusing to overwrite existing artifact: {filepath}")

    # Atomic write: write to a temp file in the same directory, then rename.
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=filepath.name + ".", suffix=".tmp", dir=str(filepath.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(filepath)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise

    logger.info(f"Wrote artifact to {filepath}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles generic non-command messages.

    Note:
    - Commands are handled by CommandHandlers.
    - This handler is only for plain text messages (non-command).
    """
    if not update.message:
        return

    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    if update.message.text:
        await update.message.reply_text("OK: Message received by inbox.")


def main() -> None:
    """Starts the Telegram bot."""
    # --- Startup Banner ---
    print("🐾 CAF Telegram Bridge is running.")
    print("- Authorized user required")
    print("- Writing inbox artifacts to: sandbox/inbox/")
    print("- Use /start or /help in Telegram for commands")

    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Always log raw updates first (non-blocking)
    app.add_handler(MessageHandler(filters.ALL, raw_update_logger), group=0)

    # Register handlers
    app.add_handler(CommandHandler("start", start_command), group=1)
    app.add_handler(CommandHandler("help", help_command), group=1)
    app.add_handler(CommandHandler("plan", plan_command), group=1)
    app.add_handler(CommandHandler("daily", daily_command), group=1)
    app.add_handler(CommandHandler("approve", approve_command), group=1)
    app.add_handler(CommandHandler("reject", reject_command), group=1)
    app.add_handler(CommandHandler("status", status_command), group=1)
    app.add_handler(CommandHandler("style", style_command), group=1)

    # Non-command text handler (kept minimal)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=1)

    logger.info("Telegram bridge started. Polling for updates...")
    app.run_polling()


if __name__ == "__main__":
    main()
