from src.gmail.client import GmailClient

# This will open a browser for Gmail OAuth
gmail = GmailClient()

# Create a test draft
draft_id = gmail.create_draft(
    message="Test draft from Python", recipient="your-email@example.com", subject="Test Draft"
)

print(f"Draft created: {draft_id}")
