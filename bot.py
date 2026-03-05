#!/usr/bin/env python3
"""Telegram bot entry point — run with: python bot.py"""

import atexit
import asyncio
import logging
import sys

from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from src.config import Config, DEFAULT_DB_PATH
from src.logger import setup_logging
from src.llm.client import LLMClient
from src.sheets.client import SheetsClient
from src.console.renderer import EmailTableRenderer
from src.agents.email_analyzer import EmailAnalyzer
from src.notion.client import NotionClient
from src.gmail.client import GmailClient
from src.db.client import LocalDB
from src.db.sync import SyncManager
from src.telegram.service import EmailBotService
from src.telegram.handlers import (
    start_handler,
    help_handler,
    analyze_handler,
    load_handler,
    emails_handler,
    actions_handler,
    reset_handler,
    message_handler,
    callback_handler,
)

log = logging.getLogger(__name__)


def main() -> None:
    setup_logging()

    try:
        config = Config.from_env()
    except ValueError as e:
        sys.exit(f"Error: {e}")

    if not config.telegram_bot_token:
        sys.exit("Error: TELEGRAM_BOT_TOKEN not set. Add it to your .env file.")
    if not config.spreadsheet_id:
        sys.exit("Error: SPREADSHEET_ID not set. Add it to your .env file.")

    log.info("Starting Telegram bot")

    # Build dependencies
    print("Authenticating with Google Sheets\u2026")
    try:
        sheets = SheetsClient(config.spreadsheet_id)
    except ValueError as e:
        sys.exit(f"Error: {e}")

    notion = None
    if config.notion_token:
        notion = NotionClient(config.notion_token)
        print("Connected to Notion.")

    gmail = None
    try:
        gmail = GmailClient()
        print("Connected to Gmail.")
    except Exception as exc:
        log.warning("Gmail not available: %s", exc)
        print(f"Gmail not configured (drafts disabled): {exc}")

    # Local DB + sync manager
    db = LocalDB(DEFAULT_DB_PATH)
    sync_manager = SyncManager(
        db,
        notion,
        notion_db_id=config.notion_db_id,
        notion_emails_db_id=config.notion_emails_db_id,
        notion_sender_db_id=config.notion_sender_db_id,
    )

    llm = LLMClient(config)
    renderer = EmailTableRenderer()
    analyzer = EmailAnalyzer(
        llm, sheets, renderer, notion, config.notion_db_id,
        config.notion_sender_db_id, config.notion_emails_db_id,
        db=db,
    )

    service = EmailBotService(
        analyzer=analyzer,
        llm=llm,
        db=db,
        sync_manager=sync_manager,
        gmail=gmail,
    )

    # Safety-net sync on process exit
    _synced = False

    def _atexit_sync():
        nonlocal _synced
        if _synced:
            return
        _synced = True
        print("\nSyncing dirty records to Notion\u2026")
        try:
            counts = sync_manager.sync_to_notion()
            total = sum(counts.values())
            if total:
                print(
                    f"Synced {counts['emails']} email(s), "
                    f"{counts['action_items']} action item(s), "
                    f"{counts['senders']} sender(s) to Notion."
                )
            else:
                print("Nothing to sync.")
        except Exception as exc:
            log.error("atexit sync failed: %s", exc)
            print(f"Sync failed: {exc}")
        finally:
            db.close()

    atexit.register(_atexit_sync)

    # Build Telegram application
    app = ApplicationBuilder().token(config.telegram_bot_token).build()
    app.bot_data["service"] = service

    # Register handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("analyze", analyze_handler))
    app.add_handler(CommandHandler("load", load_handler))
    app.add_handler(CommandHandler("emails", emails_handler))
    app.add_handler(CommandHandler("actions", actions_handler))
    app.add_handler(CommandHandler("reset", reset_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    async def post_init(application) -> None:
        await application.bot.set_my_commands([
            BotCommand("analyze", "Run email analysis pipeline"),
            BotCommand("load", "Load previous analyses from Notion"),
            BotCommand("emails", "Browse analyzed emails"),
            BotCommand("actions", "Show all action items"),
            BotCommand("reset", "Clear chat history"),
            BotCommand("help", "Show help message"),
        ])

    async def post_shutdown(application) -> None:
        nonlocal _synced
        if _synced:
            return
        _synced = True
        log.info("post_shutdown: syncing dirty records to Notion")
        try:
            counts = await asyncio.to_thread(sync_manager.sync_to_notion)
            total = sum(counts.values())
            if total:
                log.info(
                    "Synced %d email(s), %d action item(s), %d sender(s)",
                    counts["emails"], counts["action_items"], counts["senders"],
                )
                print(
                    f"\nSynced {counts['emails']} email(s), "
                    f"{counts['action_items']} action item(s), "
                    f"{counts['senders']} sender(s) to Notion."
                )
            else:
                print("\nNothing to sync.")
        except Exception as exc:
            log.error("post_shutdown sync failed: %s", exc)
        finally:
            db.close()

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    print("Bot is running. Press Ctrl+C to stop.")
    log.info("Bot polling started")
    app.run_polling()


if __name__ == "__main__":
    main()
