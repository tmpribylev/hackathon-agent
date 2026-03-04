"""Simple Gmail connector for creating draft messages."""

import base64
from email.mime.text import MIMEText
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import GMAIL_TOKEN_PATH, GMAIL_SCOPES, CREDS_PATH


class GmailClient:
    """Gmail API client for creating draft messages."""

    def __init__(self) -> None:
        """Initialize Gmail client and authenticate."""
        self._service = self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth 2.0."""
        creds = None
        if Path(GMAIL_TOKEN_PATH).exists():
            creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(CREDS_PATH).exists():
                    raise ValueError(
                        f"{CREDS_PATH} not found. "
                        "Download it from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDS_PATH, GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(GMAIL_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    def create_draft(self, message: str, recipient: str, subject: str) -> str:
        """Create a Gmail draft message.

        Args:
            message: Email body (plain text)
            recipient: Recipient email address
            subject: Email subject line

        Returns:
            Draft ID as string

        Raises:
            RuntimeError: If draft creation fails
        """
        try:
            mime_message = MIMEText(message)
            mime_message["to"] = recipient
            mime_message["subject"] = subject

            raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
            draft_body = {"message": {"raw": raw}}

            draft = (
                self._service.users()
                .drafts()
                .create(userId="me", body=draft_body)
                .execute()
            )

            return draft["id"]

        except Exception as e:
            raise RuntimeError(f"Failed to create draft: {e}") from e
