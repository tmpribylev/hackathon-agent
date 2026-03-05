# Email Analyzer

Analyzes emails from a Google Sheet using Claude — produces summaries, categories, action items, and reply strategies. Results are written back to the sheet, displayed in a color-coded console table, and optionally pushed to Notion.

Includes a **Telegram bot** for interactive browsing, chatting about analyzed emails, generating draft replies, and saving them directly as **Gmail drafts**.

## Prerequisites

- Python 3.10+
- A Google Cloud project with the **Google Sheets API** enabled
- An **Anthropic API key**
- *(Optional)* A Notion internal integration for action-item tracking
- *(Optional)* A Telegram bot token for the interactive bot
- *(Optional)* Gmail API enabled for draft creation from the Telegram bot

---

## 1. Google Cloud setup

### 1a. Enable APIs

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and select (or create) a project.
2. Navigate to **APIs & Services → Library**.
3. Enable **Google Sheets API**.
4. *(Optional)* Enable **Gmail API** — required for the "Save as Gmail Draft" feature.

### 1b. Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth client ID**.
3. Application type: **Desktop app**. Give it any name.
4. Click **Create**, then **Download JSON**.
5. Rename the downloaded file to `credentials.json` and place it in the project root.

### 1c. Update OAuth consent screen (if using Gmail)

1. Go to **APIs & Services → OAuth consent screen → Data access**
2. Add scope: `https://www.googleapis.com/auth/gmail.compose`
3. Click **Save**

> The same `credentials.json` file is shared by Sheets and Gmail. Each service gets its own cached token (`token.json` for Sheets, `gmail_token.json` for Gmail).

---

## 2. Configure the `.env` file

Copy the template and fill in your values:

```
ANTHROPIC_API_KEY=your-api-key-here
ANTHROPIC_BASE_URL=https://api.anthropic.com   # optional, change only if using a proxy

# Google Sheets
SPREADSHEET_ID=your-spreadsheet-id

# Notion (optional — for pushing action items, storing email analyses, and sender tracking)
NOTION_TOKEN=your-notion-internal-integration-token
NOTION_ACTION_ITEMS_DB_ID=your-notion-database-id
NOTION_EMAILS_DB_ID=your-notion-emails-database-id
NOTION_SENDER_DB_ID=your-notion-sender-database-id

# Telegram bot (optional)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or with a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 4. Prepare the Google Sheet

The sheet must have a **header row** (row 1) with at least these four columns (names are flexible — detection is case-insensitive):

| Required data | Accepted header names |
|---|---|
| Sender | `Sender`, `From` |
| Date | `Date`, `Sent` |
| Subject | `Subject` |
| Body | `Body`, `Body/Snippet`, `Snippet`, `Message` |

Columns can be in any order. The tool detects their positions from the header row automatically.

**Example sheet layout:**

| Sender | Date | Subject | Body/Snippet |
|---|---|---|---|
| alice@example.com | 2024-01-10 | Login issue | I can't log in on mobile... |
| bob@vendor.com | 2024-01-11 | Q1 pricing | We'd like to offer a 15% discount... |

Four new columns — **Summary**, **Category**, **Action Items**, and **Reply Strategy** — are written immediately after the last existing column (or reuse existing columns if a "Summary" header is already present).

---

## 5. Notion integration setup (optional)

Notion integration pushes action items extracted from emails into a Notion database and tracks sender history in a separate contacts database.

### 5a. Create a Notion internal integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) and click **New integration**.
2. Set type to **Internal**.
3. Copy the **Internal Integration Token**.

### 5b. Share the database

1. Open your Notion database page.
2. Click **"..."** (top-right) → **"Connections"**.
3. Add your integration by name.

### 5c. Add to `.env`

```
NOTION_TOKEN=ntn_...
NOTION_ACTION_ITEMS_DB_ID=your-notion-database-id
NOTION_EMAILS_DB_ID=your-notion-emails-database-id
NOTION_SENDER_DB_ID=your-notion-sender-database-id
```

The database ID is the 32-character hex string in the database URL:

```
https://www.notion.so/THIS_PART_IS_THE_ID?v=THIS_PART_IS_NOT_THE_ID_BUT_THE_VIEW
```

### Expected database properties

**Action Items database** (`NOTION_ACTION_ITEMS_DB_ID`):

| Property | Type | Notes |
|---|---|---|
| Action Item | `title` | Main column — action item text |
| Priority | `select` | Critical, High, Medium, Low |
| Status | `select` | Set to "Open" for new items |
| Category | `select` | Email category (Support, Sales, etc.) |
| Details | `rich_text` | Detailed explanation of the action item |
| Source Email | `rich_text` | Subject and sender of the source email |
| Due Date | `date` | Suggested deadline based on priority |

**Emails database** (`NOTION_EMAILS_DB_ID`):

| Property | Type | Notes |
|---|---|---|
| Subject | `title` | Email subject (auto-renamed from default title column) |
| Sender | `rich_text` | Sender address |
| Date | `rich_text` | Email date |
| Summary | `rich_text` | AI-generated summary |
| Category | `select` | Email category |
| Action Items | `rich_text` | Extracted action items |
| Reply Strategy | `rich_text` | Suggested reply steps |
| Body | `rich_text` | Original email body |

**Sender database** (`NOTION_SENDER_DB_ID`):

| Property | Type | Notes |
|---|---|---|
| Email | `title` | Sender email address (lookup key) |
| Sender Name | `rich_text` | Display name |
| Manual Comment | `rich_text` | User notes — never overwritten by the tool |
| AI Summary | `rich_text` | Auto-updated summary from latest analysis |
| Last Contact Date | `date` | Date of most recent email |
| Email Count | `number` | Total emails processed from this sender |

---

## 6. Run

### CLI mode

```bash
python main.py <SPREADSHEET_ID>
```

The spreadsheet ID is the long string in the sheet URL:

```
https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit
```

If `NOTION_TOKEN` and `NOTION_ACTION_ITEMS_DB_ID` are set in `.env`, action items are automatically pushed to Notion after analysis.

### Telegram bot mode

```bash
python bot.py
```

Requires `TELEGRAM_BOT_TOKEN` and `SPREADSHEET_ID` in `.env`.

### Docker

Build and run the application using Docker. This runs both the Telegram bot and schedules the CLI to run every 3 minutes via cron.

#### Build the image and run detached

```bash
docker compose up --build -d
```

This mounts the `logs/` directory and uses your `.env` file for configuration.

#### View logs

```bash
docker compose logs -f
```
And monitor the current `./logs` directory for appearing files.

> **Note:** The container runs the Telegram bot in the foreground and schedules `main.py` to run every 3 minutes via cron. Make sure `SPREADSHEET_ID` is set in your `.env` file.

---

## 7. Telegram bot

The Telegram bot provides an interactive interface for email analysis.

### Commands

| Command | Description |
|---|---|
| `/analyze` | Run email analysis pipeline |
| `/load` | Load previous analyses from Notion |
| `/emails` | Browse analyzed emails with pagination |
| `/actions` | Show all action items |
| `/reset` | Clear chat history |
| `/help` | Show help message |

### Features

- **Email browsing** — Paginated list of analyzed emails with inline keyboard navigation
- **Detail view** — View full email analysis: summary, category, action items, reply strategy
- **Draft reply generation** — Generate a professional reply using Claude, based on the email context and reply strategy
- **Save as Gmail Draft** — One-click button to save the generated reply as a draft in your Gmail inbox (requires Gmail API setup)
- **Free-text chat** — Send any message to chat about the analyzed emails with full conversation history

### Gmail draft flow

1. Open an email → tap **"Generate Draft Reply"** → Claude generates a reply
2. Tap **"Save as Gmail Draft"** → the reply is saved as a draft in Gmail, addressed to the original sender with a `Re:` subject
3. Open Gmail to review, edit, and send

> If Gmail credentials are not configured, the bot works normally — the "Save as Gmail Draft" button simply won't appear.

---

## 8. Console output

```
#     Category    Sender                    Date          Subject
──────────────────────────────────────────────────────────────────────────────────
1     Support     alice@example.com         2024-01-10    Login issue on mobile app
      → Your login problem has been escalated to the mobile team.
      Action Items:
        - [HIGH] Escalate to mobile team immediately
        - [LOW] Follow up in 48 hours
      Reply Strategy:
        1. Acknowledge the issue and apologize
        2. Confirm escalation to the mobile team
        3. Provide an ETA for resolution
```

Category colors:

| Category | Color |
|---|---|
| Support | Cyan |
| Sales | Yellow |
| Spam | Red |
| Internal | Green |
| Finance | Magenta |
| Legal | Blue |
| Other | White |

Priority colors: **[CRITICAL]** Bold Red, **[HIGH]** Red, **[MEDIUM]** Yellow, **[LOW]** Green.

---

## 9. Output written to the sheet

| Column | Header | Content |
|---|---|---|
| N | Summary | One-sentence summary of the email |
| N+1 | Category | One of: Support, Sales, Spam, Internal, Finance, Legal, Other |
| N+2 | Action Items | Prioritised action items with [HIGH]/[MEDIUM]/[LOW] tags |
| N+3 | Reply Strategy | Numbered reply steps |

Already-processed rows (those with an existing Summary value) are skipped on re-runs.

---

## Project structure

```
.
├── main.py                        # CLI entry point
├── bot.py                         # Telegram bot entry point
├── src/
│   ├── config.py                  # Config dataclass, loads .env, all constants
│   ├── logger.py                  # Logging setup (daily log files)
│   ├── llm/
│   │   └── client.py              # LLMClient (Anthropic SDK wrapper)
│   ├── sheets/
│   │   └── client.py              # SheetsClient (Google Sheets auth + read/write)
│   ├── notion/
│   │   └── client.py              # NotionClient (action items + email analyses)
│   ├── gmail/
│   │   └── client.py              # GmailClient (Gmail draft creation)
│   ├── agents/
│   │   └── email_analyzer.py      # EmailAnalyzer (prompt, parsing, orchestration)
│   ├── console/
│   │   └── renderer.py            # EmailTableRenderer (ANSI-coloured console output)
│   └── telegram/
│       ├── handlers.py            # Telegram command & callback handlers
│       ├── service.py             # EmailBotService (business logic layer)
│       ├── context_store.py       # In-memory email data store
│       ├── keyboards.py           # Inline keyboard builders
│       └── formatters.py          # Message formatting utilities
├── requirements.txt
├── pyproject.toml                 # Black & Pylint config
├── .env                           # API keys (do not commit)
├── .env.example                   # Template for .env
├── credentials.json               # Google OAuth client secret (do not commit)
├── token.json                     # Cached Sheets OAuth token (do not commit)
├── gmail_token.json               # Cached Gmail OAuth token (do not commit)
└── .gitignore
```

---

## Troubleshooting

| Error | Fix |
|---|---|
| `credentials.json not found` | Download it from Google Cloud Console (step 1b) |
| `ANTHROPIC_API_KEY not set` | Add your key to `.env` |
| `Header detection failed` | Make sure your sheet has the required column headers in row 1 |
| `403 The caller does not have permission` | Share the Google Sheet with the Google account used during OAuth |
| Token expired / auth loop | Delete `token.json` and re-run to re-authenticate |
| `NOTION_TOKEN must be set` | Add your Notion internal integration token to `.env` |
| `Could not find database with ID` | Share the Notion database with your integration (step 5b) |
| `TELEGRAM_BOT_TOKEN not set` | Add your bot token to `.env` (get one from @BotFather) |
| `Gmail not configured` | Enable Gmail API and add the compose scope (step 1a/1c) |
| Gmail re-auth needed | Delete `gmail_token.json` and restart the bot |

---

## Logging

All modules log via Python's `logging` module. Log files are written daily to `logs/YYYY-MM-DD.log`. No logs are printed to the console — console output uses `print()` directly.

%TODO

Notion connectivity is slow and expensive.
On start, cache both Notion tables to local Sqlite storage locations, these are rocket fast for address retrievals and changes.
On update/insert, mark rows as dirty.
On back sync, update only contacts with dirty rows.
