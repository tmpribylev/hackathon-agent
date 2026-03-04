"""Notion connector — OAuth auth + read/write stubs for a Notion database."""

import base64
import json
import os
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from notion_client import Client

NOTION_TOKEN_PATH = "notion_token.json"
REDIRECT_PORT = 4242
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


# ── OAuth ──────────────────────────────────────────────────────────────────────

def _exchange_code(code: str, client_id: str, client_secret: str) -> dict:
    """Exchange an authorization code for an access token."""
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/oauth/token",
        data=json.dumps({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }).encode(),
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _run_oauth_flow(client_id: str, client_secret: str) -> dict:
    """Open browser for Notion OAuth consent and return the token response."""
    auth_url = (
        "https://api.notion.com/v1/oauth/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": REDIRECT_URI,
        })
    )

    code_holder: dict = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Authorized! You can close this tab.</h2></body></html>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Authorization failed.</h2></body></html>")

        def log_message(self, format, *args):  # noqa: A002
            pass  # silence access logs

    print(f"Opening browser for Notion authorization…")
    webbrowser.open(auth_url)
    print(f"Waiting for callback on {REDIRECT_URI} (timeout: 120s)…")

    server = HTTPServer(("localhost", REDIRECT_PORT), _Handler)
    server.timeout = 120
    server.handle_request()
    server.server_close()

    if "code" not in code_holder:
        raise RuntimeError("Notion OAuth: no authorization code received.")

    return _exchange_code(code_holder["code"], client_id, client_secret)


def get_client() -> Client:
    """Return an authenticated Notion client, running OAuth if no token is cached.

    On first run, opens a browser for Notion OAuth consent and caches the
    resulting token to notion_token.json. Subsequent runs reuse the cached token.
    """
    if Path(NOTION_TOKEN_PATH).exists():
        with open(NOTION_TOKEN_PATH) as f:
            token_data = json.load(f)
        return Client(auth=token_data["access_token"])

    client_id = os.getenv("NOTION_CLIENT_ID")
    client_secret = os.getenv("NOTION_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "NOTION_CLIENT_ID and NOTION_CLIENT_SECRET must be set in .env for first-time auth."
        )

    token_data = _run_oauth_flow(client_id, client_secret)
    with open(NOTION_TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)
    print(f"Notion token cached to {NOTION_TOKEN_PATH}")

    return Client(auth=token_data["access_token"])


# ── Reader ─────────────────────────────────────────────────────────────────────

def fetch_emails(client: Client, database_id: str) -> list[dict]:
    """Return a list of email dicts from the Notion database.

    Each dict has keys: page_id, sender, date, subject, body.
    Skips pages that already have a non-empty Summary property.

    Args:
        client: Authenticated Notion client (from get_client()).
        database_id: ID of the Notion database to query.

    Returns:
        List of dicts with keys: page_id, sender, date, subject, body.
    """
    raise NotImplementedError


# ── Writer ─────────────────────────────────────────────────────────────────────

def write_result(
    client: Client,
    page_id: str,
    summary: str,
    category: str,
    action_items: str,
    reply_strategy: str,
) -> None:
    """Write analysis results back to a Notion page.

    Updates the page's Summary (rich_text), Category (select),
    Action Items (rich_text), and Reply Strategy (rich_text) properties.

    Args:
        client: Authenticated Notion client (from get_client()).
        page_id: ID of the Notion page to update.
        summary: One-sentence email summary.
        category: One of: Support, Sales, Spam, Internal, Finance, Legal, Other.
        action_items: Prioritised action items as a multi-line string.
        reply_strategy: Numbered reply steps as a multi-line string.
    """
    raise NotImplementedError
