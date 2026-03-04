"""Telegram handler functions — thin layer delegating to EmailBotService."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram.service import EmailBotService
from src.telegram.formatters import (
    format_email_summary,
    format_email_detail,
    format_action_items_message,
    format_draft_reply,
    split_message,
    _esc,
)
from src.telegram.keyboards import (
    email_list_keyboard,
    email_detail_keyboard,
    strategy_keyboard,
    draft_reply_keyboard,
)

log = logging.getLogger(__name__)

HELP_TEXT = (
    "<b>Email Analyzer Bot</b>\n\n"
    "/analyze — Run email analysis pipeline\n"
    "/load — Load previous analyses from Notion\n"
    "/emails — Browse analyzed emails\n"
    "/actions — Show all action items\n"
    "/reset — Clear chat history\n"
    "/help — Show this message\n\n"
    "Send any text message to chat about the analyzed emails."
)


def _get_service(context: ContextTypes.DEFAULT_TYPE) -> EmailBotService:
    return context.bot_data["service"]


# ── command handlers ──────────────────────────────────────────────────────────


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    await update.message.reply_text("Running email analysis\u2026")
    try:
        count = await asyncio.to_thread(service.run_analysis)
        await update.message.reply_text(f"Done! {count} email(s) analyzed.")
    except Exception as exc:
        log.error("Analysis failed: %s", exc)
        await update.message.reply_text(f"Analysis failed: {_esc(str(exc))}", parse_mode="HTML")


async def load_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    await update.message.reply_text("Loading from Notion\u2026")
    try:
        count = await asyncio.to_thread(service.load_from_notion)
        if count:
            await update.message.reply_text(f"Loaded {count} email(s) from Notion.")
        else:
            await update.message.reply_text("No emails found in Notion (or Notion not configured).")
    except Exception as exc:
        log.error("Load from Notion failed: %s", exc)
        await update.message.reply_text(f"Load failed: {_esc(str(exc))}", parse_mode="HTML")


async def emails_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    emails = service.store.all_emails()
    if not emails:
        await update.message.reply_text("No emails loaded. Use /analyze or /load first.")
        return

    lines = [format_email_summary(e) for e in emails]
    text = "<b>Analyzed Emails:</b>\n\n" + "\n".join(
        f"{i+1}. {_esc(l)}" for i, l in enumerate(lines)
    )
    for chunk in split_message(text):
        await update.message.reply_text(
            chunk, parse_mode="HTML", reply_markup=email_list_keyboard(emails)
        )


async def actions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    emails = service.store.emails_with_action_items()
    text = format_action_items_message(emails)
    for chunk in split_message(text):
        await update.message.reply_text(chunk, parse_mode="HTML")


async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    service.reset_chat(update.effective_user.id)
    await update.message.reply_text("Chat history cleared.")


# ── message handler (free-text chat) ─────────────────────────────────────────


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    user_id = update.effective_user.id
    text = update.message.text

    if not service.store.all_emails():
        await update.message.reply_text("No emails loaded yet. Use /analyze or /load first.")
        return

    try:
        response = await asyncio.to_thread(service.chat, user_id, text)
        for chunk in split_message(response):
            await update.message.reply_text(chunk)
    except Exception as exc:
        log.error("Chat failed: %s", exc)
        await update.message.reply_text("Sorry, something went wrong. Try again.")


# ── callback query handler (inline keyboards) ────────────────────────────────


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    service = _get_service(context)
    data = query.data
    prefix, _, value = data.partition(":")

    if prefix == "view":
        row_index = int(value)
        email = service.store.get(row_index)
        if not email:
            await query.edit_message_text("Email not found.")
            return
        text = format_email_detail(email)
        for chunk in split_message(text):
            await query.edit_message_text(
                chunk, parse_mode="HTML", reply_markup=email_detail_keyboard(row_index)
            )

    elif prefix == "actions":
        row_index = int(value)
        email = service.store.get(row_index)
        if not email or not email.action_items.strip():
            await query.edit_message_text(
                "No action items for this email.",
                reply_markup=email_detail_keyboard(int(value)),
            )
            return
        text = f"<b>Action Items for:</b> {_esc(email.subject)}\n\n{_esc(email.action_items)}"
        for chunk in split_message(text):
            await query.edit_message_text(
                chunk, parse_mode="HTML", reply_markup=email_detail_keyboard(row_index)
            )

    elif prefix == "strategy":
        row_index = int(value)
        email = service.store.get(row_index)
        if not email or not email.reply_strategy.strip():
            await query.edit_message_text(
                "No reply strategy for this email.",
                reply_markup=email_detail_keyboard(int(value)),
            )
            return
        text = (
            f"<b>Reply Strategy for:</b> {_esc(email.subject)}\n\n" f"{_esc(email.reply_strategy)}"
        )
        for chunk in split_message(text):
            await query.edit_message_text(
                chunk, parse_mode="HTML", reply_markup=strategy_keyboard(row_index)
            )

    elif prefix == "draft":
        row_index = int(value)
        email = service.store.get(row_index)
        if not email:
            await query.edit_message_text("Email not found.")
            return
        await query.edit_message_text("Generating draft reply\u2026")
        try:
            draft = await asyncio.to_thread(service.generate_reply_draft, row_index)
            text = format_draft_reply(email, draft)
            for chunk in split_message(text):
                await query.edit_message_text(
                    chunk, parse_mode="HTML", reply_markup=draft_reply_keyboard(row_index)
                )
        except Exception as exc:
            log.error("Draft generation failed: %s", exc)
            await query.edit_message_text(
                "Failed to generate draft. Try again.",
                reply_markup=email_detail_keyboard(row_index),
            )

    elif prefix == "back" and value == "list":
        emails = service.store.all_emails()
        if not emails:
            await query.edit_message_text("No emails loaded.")
            return
        lines = [format_email_summary(e) for e in emails]
        text = "<b>Analyzed Emails:</b>\n\n" + "\n".join(
            f"{i+1}. {_esc(l)}" for i, l in enumerate(lines)
        )
        for chunk in split_message(text):
            await query.edit_message_text(
                chunk, parse_mode="HTML", reply_markup=email_list_keyboard(emails)
            )
