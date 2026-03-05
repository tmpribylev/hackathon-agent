"""Simple Gmail connector for creating draft messages."""

import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import GMAIL_TOKEN_PATH, GMAIL_SCOPES, CREDS_PATH

log = logging.getLogger(__name__)


class GmailClient:
    """Gmail API client for creating draft messages."""

    def __init__(self) -> None:
        """Initialize Gmail client and authenticate."""
        self._service = self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth 2.0."""
        log.info("Authenticating with Gmail API")
        creds = None
        if Path(GMAIL_TOKEN_PATH).exists():
            creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                log.info("Refreshing expired Gmail credentials")
                creds.refresh(Request())
            else:
                if not Path(CREDS_PATH).exists():
                    raise ValueError(
                        f"{CREDS_PATH} not found. "
                        "Download it from Google Cloud Console."
                    )
                log.info("Running OAuth flow for new Gmail credentials")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDS_PATH, GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(GMAIL_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())

        log.info("Gmail authentication successful")
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
        log.info("Creating Gmail draft to=%s subject=%s", recipient, subject)
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

            log.info("Gmail draft created: id=%s", draft["id"])
            return draft["id"]

        except Exception as e:
            log.error("Failed to create Gmail draft: %s", e)
            raise RuntimeError(f"Failed to create draft: {e}") from e
