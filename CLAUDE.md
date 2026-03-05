# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Email Analyzer with two interfaces: a **CLI** (`main.py`) and a **Telegram bot** (`bot.py`). Reads email rows from a Google Sheet, analyzes each with Claude (summary, category, action items, reply strategy), writes results back to the sheet, and optionally pushes to Notion. The Telegram bot adds interactive browsing, chat, draft reply generation, and one-click Gmail draft saving.

## Running

```bash
python main.py <SPREADSHEET_ID>
```

Requires `credentials.json` (Google OAuth client secret) in the project root and a `.env` file with at least `ANTHROPIC_API_KEY`. Optional: `NOTION_TOKEN`, `NOTION_ACTION_ITEMS_DB_ID`, `NOTION_EMAILS_DB_ID`, and `NOTION_SENDER_DB_ID` for Notion integration.

First run triggers a browser-based OAuth flow that caches `token.json`. Delete `token.json` to re-authenticate.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in API keys
```

## Formatting and linting

```bash
black .
pylint src/ main.py
```

Config is in `pyproject.toml`: line length 100, target Python 3.10.

## Architecture

`main.py` is the CLI entry point, `bot.py` is the Telegram bot entry point. All logic lives in `src/`:

- **`src/config.py`** — `Config` dataclass, loads `.env` via `dotenv` at import time
- **`src/llm/client.py`** — `LLMClient`, thin Anthropic SDK wrapper with a `complete(prompt)` method (defaults to `claude-sonnet-4-6`)
- **`src/sheets/client.py`** — `SheetsClient`, handles Google OAuth2 auth and Sheets API read/write. Key static helpers: `find_col(headers, *candidates)` for case-insensitive header detection, `col_to_letter(col)` for 1-based column index to letter
- **`src/notion/client.py`** — `NotionClient`, manages three Notion databases: action items (`write_action_items`, `read_all_action_items`), email analyses (`write_email_analysis`, `read_email_analyses`), and sender contacts (`get_sender`, `upsert_sender`, `read_all_senders`). Uses `client.request()` for queries because the v3 `notion-client` SDK removed `databases.query()`
- **`src/gmail/client.py`** — `GmailClient`, Gmail API OAuth2 auth and draft creation
- **`src/agents/email_analyzer.py`** — `EmailAnalyzer`, the orchestrator: fetches rows, looks up sender context from the Notion sender DB, calls Claude per email, parses the structured response (Summary/Category/Action Items/Reply Strategy), writes back, upserts sender in Notion, and optionally pushes action items to Notion
- **`src/console/renderer.py`** — `EmailTableRenderer`, ANSI-colored terminal output
- **`src/telegram/`** — Telegram bot: `handlers.py` (command & callback handlers), `service.py` (`EmailBotService` business logic), `context_store.py` (in-memory email store), `keyboards.py` (inline keyboards), `formatters.py` (message formatting)
- **`src/logger.py`** — `setup_logging()`, writes daily log files to `logs/`

## Data flow

1. `SheetsClient.fetch_rows()` reads headers + data rows from Sheet1
2. `EmailAnalyzer` detects input columns (Sender/Date/Subject/Body) and output columns (Summary/Category/Reply Strategy) via `find_col`
3. Already-processed rows (those with an existing Summary) are skipped
4. If the Notion sender DB is configured, sender context (manual comments, AI summary) is looked up via `NotionClient.get_sender()` and injected into the prompt
5. Each unprocessed email goes through `LLMClient.complete()` with a structured prompt
6. Response is parsed into four sections by string matching
7. Sender is upserted in the Notion sender DB via `NotionClient.upsert_sender()` (updates AI Summary, Last Contact Date, Email Count)
8. Results are batch-written to the sheet via `SheetsClient.write_results()`
9. If Notion is configured, action items are parsed and pushed as individual pages

## Categories

Valid email categories: Support, Sales, Spam, Internal, Finance, Legal, Other. Any unrecognized value defaults to Other.

## Logging

All modules use `logging.getLogger(__name__)`. File logs go to `logs/YYYY-MM-DD.log`. No console log handler — console output is done via `print()`.

## Self-instructions

- **All constants and environment variables live in `src/config.py`.** When adding a new constant (category, model name, file path, scope, regex, etc.) or reading a new env var, put it in `src/config.py` and import it where needed. Do not scatter `os.getenv()` or magic literals across modules.
- **Keep `README.md` up to date.** When making major changes — adding a new feature, integration, entry point, command, env variable, or significantly changing existing behavior — update `README.md` to reflect those changes. This includes the feature description, setup steps, `.env` variables, project structure tree, and troubleshooting table.
