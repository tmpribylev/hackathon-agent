# Email Analyzer from Google Sheets

Reads email rows from a Google Sheet, analyzes each one with Claude (summary, category, action items, reply strategy), writes the results back to the sheet, prints a color-coded table to the console, and optionally pushes action items to a Notion database.

## Prerequisites

- Python 3.10+
- A Google Cloud project with the **Google Sheets API** enabled
- An **Anthropic API key**
- *(Optional)* A Notion internal integration for action-item tracking

---

## 1. Google Cloud setup

### 1a. Enable the Sheets API

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and select (or create) a project.
2. Navigate to **APIs & Services → Library**.
3. Search for **Google Sheets API** and click **Enable**.

### 1b. Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth client ID**.
3. Application type: **Desktop app**. Give it any name.
4. Click **Create**, then **Download JSON**.
5. Rename the downloaded file to `credentials.json` and place it in the project root.

> The first time you run the tool, a browser window will open for you to grant access. A `token.json` file is then cached so subsequent runs skip this step.

---

## 2. Configure the `.env` file

Copy the template and fill in your values:

```
ANTHROPIC_API_KEY=your-api-key-here
ANTHROPIC_BASE_URL=https://api.anthropic.com   # optional, change only if using a proxy

# Notion (optional — for pushing action items)
NOTION_TOKEN=your-notion-internal-integration-token
NOTION_ACTION_ITEMS_DB_ID=your-notion-database-id
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
| alice@example.com | 2024-01-10 | Login issue | I can't log in on mobile… |
| bob@vendor.com | 2024-01-11 | Q1 pricing | We'd like to offer a 15% discount… |

Four new columns — **Summary**, **Category**, **Action Items**, and **Reply Strategy** — are written immediately after the last existing column (or reuse existing columns if a "Summary" header is already present).

---

## 5. Notion integration setup (optional)

Notion integration pushes action items extracted from emails into a Notion database with **Action Item**, **Priority**, and **Status** properties.

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
NOTION_ACTION_ITEMS_DB_ID=319e46034062803fb038fd948abb83f9
```

The database ID is the 32-character hex string in the database URL.

### Expected database properties

| Property | Type | Notes |
|---|---|---|
| Action Item | `title` | Main column — action item text |
| Priority | `select` | Auto-created options: High, Medium, Low |
| Status | `select` | Set to "Open" for new items |

---

## 6. Run

```bash
python main.py <SPREADSHEET_ID>
```

The spreadsheet ID is the long string in the sheet URL:

```
https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit
```

If `NOTION_TOKEN` and `NOTION_ACTION_ITEMS_DB_ID` are set in `.env`, action items are automatically pushed to Notion after analysis.

---

## 7. Console output

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

Priority colors: **[HIGH]** Red, **[MEDIUM]** Yellow, **[LOW]** Green.

---

## 8. Output written to the sheet

| Column | Header | Content |
|---|---|---|
| N | Summary | One-sentence summary of the email |
| N+1 | Category | One of: Support, Sales, Spam, Internal, Finance, Legal, Other |
| N+2 | Action Items | Prioritised action items with [HIGH]/[MEDIUM]/[LOW] tags |
| N+3 | Reply Strategy | Numbered reply steps |

Already-processed rows (those with an existing Summary value) are skipped on re-runs.

---

## Gmail Connector

Standalone Gmail connector for creating draft messages.

### 1. Enable Gmail API

1. Go to [console.cloud.google.com](https://console.cloud.google.com) (same project as Sheets)
2. Navigate to **APIs & Services → Library**
3. Search for **Gmail API** and click **Enable**

### 2. Update OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen → Data access**
2. Add scope: `https://www.googleapis.com/auth/gmail.compose`
3. Click **Save**

> You can use the same `credentials.json` file — just add the Gmail API scope.

### 3. Usage

```python
from src.gmail.client import GmailClient

# Initialize (first run opens browser for OAuth)
gmail = GmailClient()

# Create a draft
draft_id = gmail.create_draft(
    message="Hello, this is the email body.",
    recipient="example@example.com",
    subject="Test Draft"
)

print(f"Draft created with ID: {draft_id}")
```

**Token caching**: After first authentication, token saved to `gmail_token.json` for future use.

> To re-authenticate, delete `gmail_token.json` and run again.

---

## Project structure

```
.
├── main.py                    # CLI entry point
├── src/
│   ├── config.py              # Config dataclass, loads .env
│   ├── llm/
│   │   └── client.py          # LLMClient (Anthropic SDK wrapper)
│   ├── sheets/
│   │   └── client.py          # SheetsClient (Google Sheets auth + read/write)
│   ├── notion/
│   │   └── client.py          # NotionClient (internal integration + action item writer)
│   ├── console/
│   │   └── renderer.py        # EmailTableRenderer (ANSI-coloured console output)
│   └── agents/
│       └── email_analyzer.py  # EmailAnalyzer (prompt, parsing, orchestration)
├── requirements.txt
├── pyproject.toml             # Black & Pylint config
├── .env                       # API keys (do not commit)
├── .env.example               # Template for .env
├── credentials.json           # Google OAuth client secret (do not commit)
├── token.json                 # Cached Google OAuth token, auto-generated (do not commit)
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
