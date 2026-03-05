"""Telegram handler functions — thin layer delegating to EmailBotService."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram.service import EmailBotService
from src.telegram.formatters import (
    format_email_list_page,
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
    "/briefing — Morning briefing with priorities\n"
    "/load — Load previous analyses from Notion\n"
    "/sync — Sync contact list from Notion\n"
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
    log.info("/start from user=%d", update.effective_user.id)
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/help from user=%d", update.effective_user.id)
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/analyze from user=%d", update.effective_user.id)
    service = _get_service(context)
    await update.message.reply_text("Running email analysis\u2026")
    try:
        count = await asyncio.to_thread(service.run_analysis)
        await update.message.reply_text(f"Done! {count} email(s) analyzed.")
    except Exception as exc:
        log.error("Analysis failed: %s", exc)
        await update.message.reply_text(f"Analysis failed: {_esc(str(exc))}", parse_mode="HTML")


async def load_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/load from user=%d", update.effective_user.id)
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


async def sync_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/sync from user=%d", update.effective_user.id)
    service = _get_service(context)
    await update.message.reply_text("Syncing contacts from Notion\u2026")
    try:
        count = await asyncio.to_thread(service.sync_contacts)
        if count:
            await update.message.reply_text(f"Synced {count} contact(s) from Notion.")
        else:
            await update.message.reply_text(
                "No contacts synced (Notion sender DB not configured or empty)."
            )
    except Exception as exc:
        log.error("Contact sync failed: %s", exc)
        await update.message.reply_text(
            f"Sync failed: {_esc(str(exc))}", parse_mode="HTML"
        )


async def briefing_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/briefing from user=%d", update.effective_user.id)
    service = _get_service(context)
    await update.message.reply_text("Generating your morning briefing…")
    try:
        text = await asyncio.to_thread(service.briefing)
        for chunk in split_message(text):
            await update.message.reply_text(chunk)
    except Exception as exc:
        log.error("Briefing failed: %s", exc)
        await update.message.reply_text(f"Briefing failed: {_esc(str(exc))}", parse_mode="HTML")


async def emails_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/emails from user=%d", update.effective_user.id)
    service = _get_service(context)
    emails = service.store.all_emails()
    if not emails:
        await update.message.reply_text("No emails loaded. Use /analyze or /load first.")
        return

    page = 0
    text = format_email_list_page(emails, page)
    for chunk in split_message(text):
        await update.message.reply_text(
            chunk, parse_mode="HTML", reply_markup=email_list_keyboard(emails, page)
        )


async def actions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/actions from user=%d", update.effective_user.id)
    service = _get_service(context)
    emails = service.store.emails_with_action_items()
    text = format_action_items_message(emails)
    for chunk in split_message(text):
        await update.message.reply_text(chunk, parse_mode="HTML")


async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("/reset from user=%d", update.effective_user.id)
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
    log.info("Callback query=%s from user=%d", data, update.effective_user.id)
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
            gmail_enabled = service._gmail is not None
            for chunk in split_message(text):
                await query.edit_message_text(
                    chunk,
                    parse_mode="HTML",
                    reply_markup=draft_reply_keyboard(row_index, gmail_enabled=gmail_enabled),
                )
        except Exception as exc:
            log.error("Draft generation failed: %s", exc)
            await query.edit_message_text(
                "Failed to generate draft. Try again.",
                reply_markup=email_detail_keyboard(row_index),
            )

    elif prefix == "gmail_draft":
        row_index = int(value)
        email = service.store.get(row_index)
        if not email:
            await query.edit_message_text("Email not found.")
            return
        await query.edit_message_text("Saving to Gmail drafts\u2026")
        try:
            draft_id = await asyncio.to_thread(service.save_draft_to_gmail, row_index)
            text = (
                f"Draft saved to Gmail!\n"
                f"<b>To:</b> {_esc(email.sender)}\n"
                f"<b>Subject:</b> Re: {_esc(email.subject)}\n"
                f"<b>Draft ID:</b> <code>{_esc(draft_id)}</code>"
            )
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=email_detail_keyboard(row_index),
            )
        except Exception as exc:
            log.error("Gmail draft save failed: %s", exc)
            await query.edit_message_text(
                f"Failed to save Gmail draft: {_esc(str(exc))}",
                parse_mode="HTML",
                reply_markup=draft_reply_keyboard(row_index, gmail_enabled=True),
            )

    elif prefix == "page":
        page = int(value)
        emails = service.store.all_emails()
        if not emails:
            await query.edit_message_text("No emails loaded.")
            return
        text = format_email_list_page(emails, page)
        for chunk in split_message(text):
            await query.edit_message_text(
                chunk, parse_mode="HTML", reply_markup=email_list_keyboard(emails, page)
            )

    elif prefix == "noop":
        return

    elif prefix == "back" and value == "list":
        emails = service.store.all_emails()
        if not emails:
            await query.edit_message_text("No emails loaded.")
            return
        text = format_email_list_page(emails, 0)
        for chunk in split_message(text):
            await query.edit_message_text(
                chunk, parse_mode="HTML", reply_markup=email_list_keyboard(emails, 0)
            )
