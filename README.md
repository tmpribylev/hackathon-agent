# Email Analyzer from Google Sheets

`I_PROMISE_I_DIDNT_PRE_CODE_THIS`

Reads email rows from a Google Sheet, analyzes each one with Claude (summary + category), writes the results back to the sheet, and prints a color-coded table to the console.

## Prerequisites

- Python 3.10+
- A Google Cloud project with the **Google Sheets API** enabled
- An **Anthropic API key**

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
ANTHROPIC_BASE_URL=https://api.anthropic.com   # change only if using a proxy or custom endpoint
```

`ANTHROPIC_BASE_URL` is optional — if it points to the default Anthropic endpoint you can leave it as-is or remove the line entirely.

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

Two new columns — **Summary** and **Category** — are written immediately after the last existing column.

---

## 5. Run

```bash
python main.py <SPREADSHEET_ID>
```

The spreadsheet ID is the long string in the sheet URL:

```
https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit
```

**Example:**

```bash
python main.py 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
```

---

## 6. Console output

```
#     Category    Sender                    Date          Subject
──────────────────────────────────────────────────────────────────────────────────
1     Support     alice@example.com         2024-01-10    Login issue on mobile app
      → Your login problem has been escalated to the mobile team.

2     Sales       bob@vendor.com            2024-01-11    Q1 pricing proposal
      → Vendor is proposing a 15% discount for an annual contract renewal.
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

---

## 7. Output written to the sheet

| Column | Header | Content |
|---|---|---|
| N (first after table) | Summary | One-sentence summary of the email |
| N+1 | Category | One of: Support, Sales, Spam, Internal, Finance, Legal, Other |

---

## Project structure

```
.
├── main.py            # CLI tool
├── requirements.txt   # Python dependencies
├── .env               # API key and base URL (do not commit)
├── credentials.json   # Google OAuth client secret (do not commit)
├── token.json         # Cached OAuth token, auto-generated (do not commit)
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
