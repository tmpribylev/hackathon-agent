"""Email triage agent — analyses emails via Claude and writes results to Sheets."""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass

from src.config import CATEGORIES, DEFAULT_CATEGORY, EMAIL_ANALYSIS_MAX_TOKENS
from src.llm.client import LLMClient
from src.sheets.client import SheetsClient
from src.console.renderer import EmailTableRenderer
from src.notion.client import NotionClient

log = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Structured result of a single email analysis."""

    row_index: int
    sender: str
    date: str
    subject: str
    body: str
    summary: str
    category: str
    action_items: str
    reply_strategy: str


class EmailAnalyzer:
    def __init__(
        self,
        llm: LLMClient,
        sheets: SheetsClient,
        renderer: EmailTableRenderer,
        notion: NotionClient | None = None,
        notion_db_id: str | None = None,
        notion_sender_db_id: str | None = None,
    ) -> None:
        self._llm = llm
        self._sheets = sheets
        self._renderer = renderer
        self._notion = notion
        self._notion_db_id = notion_db_id
        self._notion_sender_db_id = notion_sender_db_id
        self._today = datetime.date.today().isoformat()

    # ── public entry points ───────────────────────────────────────────────────

    def analyze(self) -> list[AnalysisResult]:
        """Fetch emails from the sheet, analyze unprocessed ones, write results back.

        Returns a list of AnalysisResult for every newly analyzed email.
        """
        log.info("Fetching rows from sheet")
        headers, rows = self._sheets.fetch_rows()
        log.info("Fetched %d row(s), headers: %s", len(rows), headers)

        col = self.detect_columns(headers)
        out_summary_i, out_start_col = self.detect_output_columns(headers)
        already_done = self._build_already_done(rows, out_summary_i)

        if already_done:
            log.info("Skipping %d already-processed row(s)", len(already_done))

        raw_results: list[tuple[str, str, str, str] | None] = []
        analysis_results: list[AnalysisResult] = []
        to_process = len(rows) - len(already_done)
        log.info("Will analyze %d email(s)", to_process)

        processed = 0
        for i, row in enumerate(rows):
            if i in already_done:
                raw_results.append(None)
                continue
            processed += 1
            sender = row[col["sender"]]
            date = row[col["date"]]
            subject = row[col["subject"]]
            body = row[col["body"]]
            log.info("Analyzing email %d/%d: %s", processed, to_process, subject)
            result = self._analyze_email(sender, date, subject, body)
            log.info("Result — category=%s, summary=%s", result[1], result[0])
            raw_results.append(result)
            analysis_results.append(
                AnalysisResult(
                    row_index=i,
                    sender=sender,
                    date=date,
                    subject=subject,
                    body=body,
                    summary=result[0],
                    category=result[1],
                    action_items=result[2],
                    reply_strategy=result[3],
                )
            )

        if to_process > 0:
            log.info("Writing results back to sheet")
            self._sheets.write_results(raw_results, out_start_col)

        if to_process > 0 and self._notion and self._notion_db_id:
            self._push_action_items_to_notion(rows, raw_results, col)

        return analysis_results

    def run(self) -> None:
        """CLI entry point: analyze + render console output."""
        print("Fetching rows\u2026")
        headers, rows = self._sheets.fetch_rows()

        col = self.detect_columns(headers)
        out_summary_i, out_start_col = self.detect_output_columns(headers)
        already_done = self._build_already_done(rows, out_summary_i)

        if already_done:
            print(f"Skipping {len(already_done)} already-processed row(s).")

        results: list[tuple[str, str, str, str] | None] = []
        to_process = len(rows) - len(already_done)
        print(f"Analyzing {to_process} email(s) with Claude\u2026\n")

        processed = 0
        for i, row in enumerate(rows):
            if i in already_done:
                results.append(None)
                continue
            processed += 1
            sender = row[col["sender"]]
            date = row[col["date"]]
            subject = row[col["subject"]]
            body = row[col["body"]]
            log.info("Analyzing email %d/%d: %s", processed, to_process, subject)
            print(f"  [{processed}/{to_process}] {subject[:60]}", end="\r", flush=True)
            summary, category, action_items, reply_strategy, email_address = (
                self._analyze_email(sender, date, subject, body)
            )
            log.info("Result — category=%s, summary=%s", category, summary)
            results.append((summary, category, action_items, reply_strategy))

            # Upsert sender in Notion
            if self._notion and self._notion_sender_db_id:
                try:
                    self._notion.upsert_sender(
                        self._notion_sender_db_id,
                        email_address,
                        sender,
                        summary,
                        date,
                    )
                except Exception as exc:
                    log.error("Failed to upsert sender for row %d: %s", i + 2, exc)

        print(" " * 80, end="\r")  # clear progress line

        if to_process > 0:
            log.info("Writing results back to sheet")
            print("Writing results back to sheet\u2026")
            self._sheets.write_results(results, out_start_col)

        if to_process > 0 and self._notion and self._notion_db_id:
            self._push_action_items_to_notion(rows, results, col, verbose=True)

        self._renderer.render(rows, results, col["sender"], col["date"], col["subject"])
        last_col = SheetsClient.col_to_letter(out_start_col + 2)
        log.info("Done. %d analyzed, %d skipped.", to_process, len(already_done))
        print(
            f"Done. {to_process} analyzed, {len(already_done)} skipped. "
            f"Columns {SheetsClient.col_to_letter(out_start_col)}\u2013{last_col}.\n"
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def detect_columns(headers: list[str]) -> dict[str, int]:
        find = SheetsClient.find_col
        return {
            "sender": find(headers, "sender", "from"),
            "date": find(headers, "date", "sent"),
            "subject": find(headers, "subject"),
            "body": find(headers, "body", "body/snippet", "snippet", "message"),
        }

    @staticmethod
    def detect_output_columns(headers: list[str]) -> tuple[int | None, int]:
        """Return (out_summary_index_or_None, 1_based_start_col)."""
        try:
            out_summary_i = SheetsClient.find_col(headers, "summary")
            return out_summary_i, out_summary_i + 1
        except ValueError:
            return None, len(headers) + 1

    @staticmethod
    def _build_already_done(rows: list[list[str]], out_summary_i: int | None) -> set[int]:
        if out_summary_i is None:
            return set()
        return {idx for idx, row in enumerate(rows) if row[out_summary_i].strip()}

    @staticmethod
    def _extract_email_address(sender: str) -> str:
        """Extract email from sender string.

        Handles formats: "email@example.com" or "Name <email@example.com>"
        Returns lowercase email address.
        """
        match = re.search(r'<(.+?)>', sender)
        if match:
            return match.group(1).strip().lower()
        return sender.strip().lower()

    @staticmethod
    def _build_context_section(manual_comment: str, ai_summary: str) -> str:
        """Build context string with priority labels.

        Returns empty string if both are empty.
        """
        parts = []
        if manual_comment:
            parts.append(f"[TOP PRIORITY] Manual Notes: {manual_comment}")
        if ai_summary:
            parts.append(f"[MEDIUM PRIORITY] AI Summary: {ai_summary}")

        if not parts:
            return ""

        return "Previous interaction context:\n" + "\n".join(parts) + "\n\n"
      
    def _push_action_items_to_notion(
        self,
        rows: list[list[str]],
        results: list[tuple[str, str, str, str] | None],
        col: dict[str, int],
        *,
        verbose: bool = False,
    ) -> None:
        total_items = 0
        failed = 0
        for i, result in enumerate(results):
            if result is None:
                continue
            _, category, action_items, _ = result
            row = rows[i]
            source = f"{row[col['subject']]} \u2014 {row[col['sender']]}"
            if action_items:
                try:
                    total_items += self._notion.write_action_items(
                        self._notion_db_id,
                        action_items,
                        category=category,
                        source_email=source,
                    )
                except Exception as exc:
                    failed += 1
                    log.error("Notion write failed for row %d: %s", i + 2, exc)
                    if verbose:
                        print(f"\n  \u26a0 Notion write failed for row {i + 2}: {exc}")
        log.info("Pushed %d action item(s) to Notion (%d failed)", total_items, failed)
        if verbose:
            msg = f"Pushed {total_items} action item(s) to Notion."
            if failed:
                msg += f" ({failed} failed)"
            print(msg)
      
    def _build_prompt(self, sender: str, date: str, subject: str, body: str, context: str = "") -> str:
        return (
            "You are an email triage assistant. Analyze the email and respond using "
            "EXACTLY this format (keep the section headers verbatim, no extra blank "
            "lines between headers and content):\n\n"
            "Summary: <one sentence describing what the email is about>\n"
            "Category: <exactly one of: Support, Sales, Spam, Internal, Finance, "
            "Legal, Other>\n"
            "Action Items:\n"
            "- [CRITICAL] <short action title>\n"
            "  Details: <detailed explanation of what needs to be done and why>\n"
            '  Due: <YYYY-MM-DD suggested deadline based on urgency, or "none">\n'
            "- [HIGH] <short action title>\n"
            "  Details: <detailed explanation>\n"
            '  Due: <YYYY-MM-DD or "none">\n'
            "- [MEDIUM] <short action title>\n"
            "  Details: <detailed explanation>\n"
            '  Due: <YYYY-MM-DD or "none">\n'
            "Reply Strategy:\n"
            "1. <first step>\n"
            "2. <second step>\n"
            "3. <third step \u2014 add more steps as needed>\n\n"
            "Rules:\n"
            "- Omit action item lines that do not apply (do not write empty bullets).\n"
            "- Each action item MUST have a Details line and a Due line.\n"
            "- CRITICAL is reserved for truly urgent, business-critical matters that "
            "demand immediate action (e.g. security incidents, legal deadlines, "
            "production outages). Do not over-use it.\n"
            "- The Due date should be realistic based on urgency: CRITICAL = today or "
            "next business day, HIGH = within 1-2 days, "
            'MEDIUM = within a week, LOW = within 2 weeks. Use "none" only if truly '
            "no deadline applies.\n"
            "- The reply strategy must be a concrete, ordered sequence of communication "
            "steps (e.g. acknowledge, resolve urgent items, start a side thread, "
            "request a call, reply with minutes and final decision). Tailor the steps "
            "to this specific email.\n"
            "- No extra commentary outside the four sections.\n\n"
            f"Today's date: {self._today}\n"
            f"{context}"
            "[CURRENT EMAIL]\n"
            f"From: {sender}\n"
            f"Date: {date}\n"
            f"Subject: {subject}\n"
            f"Body: {body}"
        )

    def _analyze_email(
        self, sender: str, date: str, subject: str, body: str
    ) -> tuple[str, str, str, str, str]:
        """Return (summary, category, action_items, reply_strategy, email_address)."""
        email_address = self._extract_email_address(sender)
        context = ""

        # Lookup sender context if Notion configured
        if self._notion and self._notion_sender_db_id:
            sender_data = self._notion.get_sender(self._notion_sender_db_id, email_address)
            if sender_data:
                context = self._build_context_section(
                    sender_data.get("manual_comment", ""),
                    sender_data.get("ai_summary", "")
                )

        prompt = self._build_prompt(sender, date, subject, body, context)
        text = self._llm.complete(prompt, max_tokens=EMAIL_ANALYSIS_MAX_TOKENS)

        def extract_section(label: str, next_label: str | None) -> str:
            start = text.find(label)
            if start == -1:
                return ""
            start += len(label)
            if next_label:
                end = text.find(f"\n{next_label}", start)
            else:
                end = -1
            content = text[start:end] if end != -1 else text[start:]
            return content.strip()

        summary = ""
        category = "Other"
        for line in text.splitlines():
            if line.startswith("Summary:"):
                summary = line[len("Summary:") :].strip()
            elif line.startswith("Category:"):
                raw = line[len("Category:") :].strip()
                category = raw if raw in CATEGORIES else DEFAULT_CATEGORY

        action_items = extract_section("Action Items:", "Reply Strategy:")
        reply_strategy = extract_section("Reply Strategy:", None)

        return summary, category, action_items, reply_strategy, email_address
