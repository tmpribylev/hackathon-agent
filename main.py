#!/usr/bin/env python3
"""Email Analyzer — reads emails from Google Sheets, analyzes with Claude, writes results back."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import anthropic
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_PATH = "token.json"
CREDS_PATH = "credentials.json"

CATEGORIES = {"Support", "Sales", "Spam", "Internal", "Finance", "Legal", "Other"}

CATEGORY_COLORS = {
    "Support": "\033[96m",    # cyan
    "Sales":   "\033[93m",    # yellow
    "Spam":    "\033[91m",    # red
    "Internal":"\033[92m",    # green
    "Finance": "\033[95m",    # magenta
    "Legal":   "\033[94m",    # blue
    "Other":   "\033[97m",    # white
}
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"

PRIORITY_COLORS = {
    "HIGH":   "\033[91m",  # red
    "MEDIUM": "\033[93m",  # yellow
    "LOW":    "\033[92m",  # green
}


# ── Google Sheets helpers ──────────────────────────────────────────────────────

def get_sheets_service():
    creds = None
    if Path(TOKEN_PATH).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDS_PATH).exists():
                sys.exit(
                    f"Error: {CREDS_PATH} not found. "
                    "Download it from Google Cloud Console and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def col_to_letter(col: int) -> str:
    """Convert 1-based column index to spreadsheet letter (1→A, 27→AA, …)."""
    result = ""
    while col > 0:
        col, remainder = divmod(col - 1, 26)
        result = chr(65 + remainder) + result
    return result


def fetch_rows(service, spreadsheet_id: str):
    """Return (headers, rows) from the first sheet.

    headers — list of str (row 1)
    rows    — list of list of str (rows 2+), already padded to header length
    """
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range="Sheet1",
    ).execute()
    values = result.get("values", [])
    if not values:
        sys.exit("Sheet is empty.")
    headers = [h.strip() for h in values[0]]
    rows = []
    for row in values[1:]:
        # Pad short rows so every row has the same width as headers
        padded = row + [""] * (len(headers) - len(row))
        rows.append(padded)
    return headers, rows


def find_col(headers: list[str], *candidates: str) -> int:
    """Return 0-based index of the first matching header (case-insensitive)."""
    lower = [h.lower() for h in headers]
    for name in candidates:
        try:
            return lower.index(name.lower())
        except ValueError:
            continue
    raise ValueError(f"Could not find any of {candidates} in headers: {headers}")


# ── Claude analysis ────────────────────────────────────────────────────────────

def analyze_email(
    client: anthropic.Anthropic, sender: str, date: str, subject: str, body: str
) -> tuple[str, str, str, str]:
    """Call Claude and return (summary, category, action_items, reply_strategy)."""
    prompt = (
        "You are an email triage assistant. Analyze the email and respond using EXACTLY this format "
        "(keep the section headers verbatim, no extra blank lines between headers and content):\n\n"
        "Summary: <one sentence describing what the email is about>\n"
        "Category: <exactly one of: Support, Sales, Spam, Internal, Finance, Legal, Other>\n"
        "Action Items:\n"
        "- [HIGH] <urgent action if any>\n"
        "- [MEDIUM] <normal-priority action if any>\n"
        "- [LOW] <low-priority action if any>\n"
        "Reply Strategy:\n"
        "1. <first step>\n"
        "2. <second step>\n"
        "3. <third step — add more steps as needed>\n\n"
        "Rules:\n"
        "- Omit action item lines that do not apply (do not write empty bullets).\n"
        "- The reply strategy must be a concrete, ordered sequence of communication steps "
        "(e.g. acknowledge, resolve urgent items, start a side thread, request a call, "
        "reply with minutes and final decision). Tailor the steps to this specific email.\n"
        "- No extra commentary outside the four sections.\n\n"
        f"From: {sender}\n"
        f"Date: {date}\n"
        f"Subject: {subject}\n"
        f"Body: {body}"
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()

    def extract_section(label: str, next_label: str | None) -> str:
        """Return the body of a section between label and the next label (or end)."""
        start_marker = f"{label}\n"
        start = text.find(start_marker)
        if start == -1:
            return ""
        start += len(start_marker)
        if next_label:
            end = text.find(f"\n{next_label}\n", start)
            if end == -1:
                end = text.find(f"\n{next_label}:", start)
        else:
            end = -1
        return text[start:end].strip() if end != -1 else text[start:].strip()

    # Parse single-line fields
    summary = ""
    category = "Other"
    for line in text.splitlines():
        if line.startswith("Summary:"):
            summary = line[len("Summary:"):].strip()
        elif line.startswith("Category:"):
            raw = line[len("Category:"):].strip()
            category = raw if raw in CATEGORIES else "Other"

    action_items = extract_section("Action Items:", "Reply Strategy:")
    reply_strategy = extract_section("Reply Strategy:", None)

    return summary, category, action_items, reply_strategy


# ── Sheet write-back ───────────────────────────────────────────────────────────

def write_results(
    service,
    spreadsheet_id: str,
    results: list[tuple[str, str, str, str] | None],
    start_col: int,
):
    """Write (summary, category, action_items, reply_strategy) back to the sheet.

    start_col — 1-based column index of the Summary column.
    Row 1 gets headers; rows 2+ get data. None entries are skipped (already processed).
    """
    cols = [col_to_letter(start_col + i) for i in range(4)]
    first, last = cols[0], cols[-1]

    data = [
        {
            "range": f"Sheet1!{first}1:{last}1",
            "values": [["Summary", "Category", "Action Items", "Reply Strategy"]],
        }
    ]
    for i, result in enumerate(results, start=2):
        if result is None:
            continue
        summary, category, action_items, reply_strategy = result
        data.append(
            {
                "range": f"Sheet1!{first}{i}:{last}{i}",
                "values": [[summary, category, action_items, reply_strategy]],
            }
        )

    body = {"valueInputOption": "RAW", "data": data}
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()


# ── Console output ─────────────────────────────────────────────────────────────

def _color_priority_line(line: str) -> str:
    """Wrap the [PRIORITY] tag in its ANSI color."""
    for priority, color in PRIORITY_COLORS.items():
        tag = f"[{priority}]"
        if tag in line:
            return line.replace(tag, f"{color}{BOLD}{tag}{RESET}", 1)
    return line


def print_table(
    rows: list[list[str]],
    results: list[tuple[str, str, str, str] | None],
    headers: list[str],
    sender_i: int,
    date_i: int,
    subject_i: int,
):
    col_widths = {"category": 10, "sender": 24, "date": 12, "subject": 34}
    sep_width = sum(col_widths.values()) + len(col_widths) * 3 + 2

    header_line = (
        f"{'#':<5}"
        f"{'Category':<{col_widths['category']}}  "
        f"{'Sender':<{col_widths['sender']}}  "
        f"{'Date':<{col_widths['date']}}  "
        f"{'Subject':<{col_widths['subject']}}"
    )
    print(f"\n{BOLD}{header_line}{RESET}")
    print("─" * sep_width)

    indent = "      "
    for idx, (row, result) in enumerate(zip(rows, results), start=1):
        sender  = row[sender_i][:col_widths["sender"]]
        date    = row[date_i][:col_widths["date"]]
        subject = row[subject_i][:col_widths["subject"]]

        if result is None:
            print(
                f"{DIM}{idx:<5}"
                f"{'—':<{col_widths['category']}}  "
                f"{sender:<{col_widths['sender']}}  "
                f"{date:<{col_widths['date']}}  "
                f"{subject:<{col_widths['subject']}}"
                f"  (already processed){RESET}"
            )
            print()
            continue

        summary, category, action_items, reply_strategy = result
        color = CATEGORY_COLORS.get(category, RESET)

        print(
            f"{idx:<5}"
            f"{color}{category:<{col_widths['category']}}{RESET}  "
            f"{sender:<{col_widths['sender']}}  "
            f"{date:<{col_widths['date']}}  "
            f"{subject:<{col_widths['subject']}}"
        )
        print(f"{indent}{DIM}→ {summary}{RESET}")

        if action_items:
            print(f"{indent}{BOLD}Action Items:{RESET}")
            for line in action_items.splitlines():
                line = line.strip()
                if line:
                    print(f"{indent}  {_color_priority_line(line)}")

        if reply_strategy:
            print(f"{indent}{BOLD}Reply Strategy:{RESET}")
            for line in reply_strategy.splitlines():
                line = line.strip()
                if line:
                    print(f"{indent}  {DIM}{line}{RESET}")

        print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze emails in a Google Sheet with Claude and write results back."
    )
    parser.add_argument("spreadsheet_id", help="Google Sheets spreadsheet ID")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set. Add it to your .env file.")
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    print("Authenticating with Google Sheets…")
    service = get_sheets_service()

    print("Fetching rows…")
    headers, rows = fetch_rows(service, args.spreadsheet_id)

    # Detect required columns
    try:
        sender_i  = find_col(headers, "sender", "from")
        date_i    = find_col(headers, "date", "sent")
        subject_i = find_col(headers, "subject")
        body_i    = find_col(headers, "body", "body/snippet", "snippet", "message")
    except ValueError as e:
        sys.exit(f"Header detection failed: {e}")

    # Detect output columns — reuse existing headers if present, else append after table.
    # fetch_rows() pads every row to len(headers), so existing output values are already in memory.
    try:
        out_summary_i = find_col(headers, "summary")
        out_start_col = out_summary_i + 1  # 1-based
    except ValueError:
        out_summary_i = None
        out_start_col = len(headers) + 1

    if out_summary_i is not None:
        already_done = {
            idx for idx, row in enumerate(rows) if row[out_summary_i].strip()
        }
    else:
        already_done = set()

    if already_done:
        print(f"Skipping {len(already_done)} already-processed row(s).")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)
    results: list[tuple[str, str, str, str] | None] = []

    to_process = len(rows) - len(already_done)
    print(f"Analyzing {to_process} email(s) with Claude…\n")
    processed = 0
    for i, row in enumerate(rows, start=1):
        if (i - 1) in already_done:
            results.append(None)
            continue
        processed += 1
        sender  = row[sender_i]
        date    = row[date_i]
        subject = row[subject_i]
        body    = row[body_i]
        print(f"  [{processed}/{to_process}] {subject[:60]}", end="\r", flush=True)
        results.append(analyze_email(client, sender, date, subject, body))
    print(" " * 80, end="\r")  # clear progress line

    if to_process > 0:
        print("Writing results back to sheet…")
        write_results(service, args.spreadsheet_id, results, out_start_col)

    print_table(rows, results, headers, sender_i, date_i, subject_i)
    last_col = col_to_letter(out_start_col + 3)
    print(f"Done. {to_process} analyzed, {len(already_done)} skipped. "
          f"Columns {col_to_letter(out_start_col)}–{last_col}.\n")


if __name__ == "__main__":
    main()
