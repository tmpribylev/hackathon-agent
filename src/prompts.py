"""Centralised prompt templates for all LLM calls."""

EMAIL_ANALYSIS_PROMPT = (
    "You are an email triage assistant. Analyze the email and respond using "
    "EXACTLY this format (keep the section headers verbatim, no extra blank "
    "lines between headers and content):\n\n"
    "Summary: <one sentence describing what the email is about>\n"
    "Category: <exactly one of: Support, Sales, Spam, Internal, Finance, "
    "Legal, Other>\n"
    "Action Items:\n"
    "- [CRITICAL] <short action title>\n"
    "  Details: <detailed explanation of what needs to be done and why>\n"
    '  Due: <YYYY-MM-DD suggested deadline based on urgency, or "none">\n'
    "- [HIGH] <short action title>\n"
    "  Details: <detailed explanation>\n"
    '  Due: <YYYY-MM-DD or "none">\n'
    "- [MEDIUM] <short action title>\n"
    "  Details: <detailed explanation>\n"
    '  Due: <YYYY-MM-DD or "none">\n'
    "Reply Strategy:\n"
    "1. <first step>\n"
    "2. <second step>\n"
    "3. <third step — add more steps as needed>\n\n"
    "Rules:\n"
    "- Omit action item lines that do not apply (do not write empty bullets).\n"
    "- Each action item MUST have a Details line and a Due line.\n"
    "- CRITICAL is reserved for truly urgent, business-critical matters that "
    "demand immediate action (e.g. security incidents, legal deadlines, "
    "production outages). Do not over-use it.\n"
    "- The Due date should be realistic based on urgency: CRITICAL = today or "
    "next business day, HIGH = within 1-2 days, "
    'MEDIUM = within a week, LOW = within 2 weeks. Use "none" only if truly '
    "no deadline applies.\n"
    "- The reply strategy must be a concrete, ordered sequence of communication "
    "steps (e.g. acknowledge, resolve urgent items, start a side thread, "
    "request a call, reply with minutes and final decision). Tailor the steps "
    "to this specific email.\n"
    "- No extra commentary outside the four sections.\n\n"
    "Today's date: {today}\n"
    "{context}"
    "[CURRENT EMAIL]\n"
    "From: {sender}\n"
    "Date: {date}\n"
    "Subject: {subject}\n"
    "Body: {body}"
)

DRAFT_REPLY_PROMPT = (
    "Write a professional email reply based on the original email and the "
    "reply strategy below. Write only the reply body — no subject line, "
    "no commentary.\n\n"
    "Original email:\n"
    "From: {sender}\n"
    "Date: {date}\n"
    "Subject: {subject}\n"
    "Body: {body}\n\n"
    "Reply Strategy:\n{reply_strategy}\n\n"
    "Draft reply:"
)

CHAT_SYSTEM_PROMPT_HEADER = (
    "You are an email assistant. Below are the analyzed emails. "
    "Answer questions about them accurately and concisely.\n\n"
)

SENDER_SUMMARY_PROMPT = (
    "You are an assistant that maintains a concise profile of an email "
    "contact. Your job is to write or update a short summary about a person "
    "based on their email correspondence.\n\n"
    "Rules:\n"
    "- The summary is about the PERSON, not about any single email.\n"
    "- Focus on: who they are (role, organization), communication style, "
    "relationship to us, and any recurring topics or patterns.\n"
    "- If a previous summary exists, treat it as the primary source of truth. "
    "Only make incremental adjustments based on the new email.\n"
    "- One atypical email should NOT rewrite the overall characterization.\n"
    "- Keep the summary to 2-4 sentences.\n"
    "- Do not include specific action items or email content details.\n\n"
    "Sender: {sender_name}\n"
    "Previous summary: {previous_summary}\n"
    "Latest email summary: {email_summary}\n\n"
    "Updated person summary:"
)
