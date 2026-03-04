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

def analyze_email(client: anthropic.Anthropic, sender: str, date: str, subject: str, body: str) -> tuple[str, str]:
    """Call Claude and return (summary, category)."""
    prompt = (
        "You are an email triage assistant. Analyze the email below and respond with exactly two lines:\n"
        "Line 1 — a single sentence summarizing what the email is about.\n"
        "Line 2 — exactly one category from this list: Support, Sales, Spam, Internal, Finance, Legal, Other.\n"
        "No extra text, punctuation, or explanation.\n\n"
        f"From: {sender}\n"
        f"Date: {date}\n"
        f"Subject: {subject}\n"
        f"Body: {body}"
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    parts = text.split("\n", 1)
    summary = parts[0].strip() if parts else ""
    category = parts[1].strip() if len(parts) > 1 else "Other"
    if category not in CATEGORIES:
        category = "Other"
    return summary, category


# ── Sheet write-back ───────────────────────────────────────────────────────────

def write_results(service, spreadsheet_id: str, results: list[tuple[str, str]], start_col: int):
    """Write (summary, category) pairs back to the sheet.

    start_col — 1-based column index of the Summary column.
    Row 1 gets headers; rows 2+ get data.
    """
    summary_col = col_to_letter(start_col)
    category_col = col_to_letter(start_col + 1)

    data = [
        {
            "range": f"Sheet1!{summary_col}1:{category_col}1",
            "values": [["Summary", "Category"]],
        }
    ]
    for i, (summary, category) in enumerate(results, start=2):
        data.append(
            {
                "range": f"Sheet1!{summary_col}{i}:{category_col}{i}",
                "values": [[summary, category]],
            }
        )

    body = {
        "valueInputOption": "RAW",
        "data": data,
    }
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()


# ── Console output ─────────────────────────────────────────────────────────────

def print_table(rows: list[list[str]], results: list[tuple[str, str]], headers: list[str],
                sender_i: int, date_i: int, subject_i: int):
    col_widths = {
        "category": 10,
        "sender":   24,
        "date":     12,
        "subject":  34,
    }
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

    for idx, (row, (summary, category)) in enumerate(zip(rows, results), start=1):
        color = CATEGORY_COLORS.get(category, RESET)
        sender  = row[sender_i][:col_widths["sender"]]
        date    = row[date_i][:col_widths["date"]]
        subject = row[subject_i][:col_widths["subject"]]

        print(
            f"{idx:<5}"
            f"{color}{category:<{col_widths['category']}}{RESET}  "
            f"{sender:<{col_widths['sender']}}  "
            f"{date:<{col_widths['date']}}  "
            f"{subject:<{col_widths['subject']}}"
        )
        print(f"      {DIM}→ {summary}{RESET}")
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

    # Output columns start right after the existing table
    out_start_col = len(headers) + 1  # 1-based

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)
    results: list[tuple[str, str]] = []

    print(f"Analyzing {len(rows)} email(s) with Claude…\n")
    for i, row in enumerate(rows, start=1):
        sender  = row[sender_i]
        date    = row[date_i]
        subject = row[subject_i]
        body    = row[body_i]
        print(f"  [{i}/{len(rows)}] {subject[:60]}", end="\r", flush=True)
        summary, category = analyze_email(client, sender, date, subject, body)
        results.append((summary, category))
    print(" " * 80, end="\r")  # clear progress line

    print("Writing results back to sheet…")
    write_results(service, args.spreadsheet_id, results, out_start_col)

    print_table(rows, results, headers, sender_i, date_i, subject_i)
    print(f"Done. Wrote Summary + Category to columns "
          f"{col_to_letter(out_start_col)}–{col_to_letter(out_start_col + 1)}.\n")


if __name__ == "__main__":
    main()
