"""Google Sheets authentication and read/write operations."""

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class SheetsClient:
    TOKEN_PATH = "token.json"
    CREDS_PATH = "credentials.json"
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, spreadsheet_id: str) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._service = self._authenticate()

    def _authenticate(self):
        log.info("Authenticating with Google Sheets API")
        creds = None
        if Path(self.TOKEN_PATH).exists():
            creds = Credentials.from_authorized_user_file(self.TOKEN_PATH, self.SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                log.info("Refreshing expired credentials")
                creds.refresh(Request())
            else:
                if not Path(self.CREDS_PATH).exists():
                    raise ValueError(
                        f"{self.CREDS_PATH} not found. "
                        "Download it from Google Cloud Console and place it here."
                    )
                log.info("Running OAuth flow for new credentials")
                flow = InstalledAppFlow.from_client_secrets_file(self.CREDS_PATH, self.SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        log.info("Google Sheets authentication successful")
        return build("sheets", "v4", credentials=creds)

    def fetch_rows(self, sheet: str = "Sheet1") -> tuple[list[str], list[list[str]]]:
        """Return (headers, rows) from the given sheet.

        headers — list of str (row 1)
        rows    — list of list of str (rows 2+), padded to header length
        """
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=sheet)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            raise ValueError("Sheet is empty.")
        headers = [h.strip() for h in values[0]]
        rows = []
        for row in values[1:]:
            padded = row + [""] * (len(headers) - len(row))
            rows.append(padded)
        return headers, rows

    def write_results(
        self,
        results: list[tuple[str, str, str, str] | None],
        start_col: int,
        sheet: str = "Sheet1",
    ) -> None:
        """Write (summary, category, reply_strategy) back to the sheet.

        start_col — 1-based column index of the Summary column.
        Row 1 gets headers; rows 2+ get data.  None entries are skipped.
        """
        cols = [self.col_to_letter(start_col + i) for i in range(3)]
        first, last = cols[0], cols[-1]

        data = [
            {
                "range": f"{sheet}!{first}1:{last}1",
                "values": [["Summary", "Category", "Reply Strategy"]],
            }
        ]
        for i, result in enumerate(results, start=2):
            if result is None:
                continue
            summary, category, _, reply_strategy = result
            data.append(
                {
                    "range": f"{sheet}!{first}{i}:{last}{i}",
                    "values": [[summary, category, reply_strategy]],
                }
            )

        body = {"valueInputOption": "RAW", "data": data}
        log.info("Writing %d range(s) to sheet", len(data))
        self._service.spreadsheets().values().batchUpdate(
            spreadsheetId=self._spreadsheet_id, body=body
        ).execute()

    @staticmethod
    def col_to_letter(col: int) -> str:
        """Convert 1-based column index to spreadsheet letter (1→A, 27→AA, …)."""
        result = ""
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            result = chr(65 + remainder) + result
        return result

    @staticmethod
    def find_col(headers: list[str], *candidates: str) -> int:
        """Return 0-based index of the first matching header (case-insensitive)."""
        lower = [h.lower() for h in headers]
        for name in candidates:
            try:
                return lower.index(name.lower())
            except ValueError:
                continue
        raise ValueError(f"Could not find any of {candidates} in headers: {headers}")
