import imaplib
import os
import email
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

import re
from dotenv import load_dotenv

from .models import GmailEmail

# Load .env from project root so credentials are always found
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("EMAIL_APP_PASS")


def connect_mail():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, APP_PASSWORD)
    mail.select("inbox")
    return mail


def get_last_sync_date():
    """
    Return the date of the most recently saved email.
    Used to fetch only NEW emails since the last batch run.
    """
    latest = GmailEmail.objects.order_by("-created_at").values_list("created_at", flat=True).first()
    return latest


# Only fetch job-alert emails from these senders (IMAP FROM matches substrings in the From header)
JOB_ALERT_SENDERS = [
    "Minhaj ali khan",
    "upwork",
    "fiverr",
]


def fetch_email_ids(mail, since_date=None):
    """
    Fetch inbox email IDs since since_date, filtered to job-alert senders only.
    Combines FROM + SINCE so each daily batch only pulls new mail from these sources.
    """
    if since_date:
        # IMAP SINCE uses date only (ignores time) — subtract 1 day to avoid missing same-day emails
        imap_date = (since_date - timedelta(days=1)).strftime("%d-%b-%Y")
    else:
        # First run: pull last 30 days instead of entire inbox history
        imap_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")

    all_ids = set()
    for sender in JOB_ALERT_SENDERS:
        query = f'(FROM "{sender}" SINCE "{imap_date}")'
        status, messages = mail.search(None, query)
        if status == "OK" and messages[0]:
            for eid in messages[0].split():
                all_ids.add(eid)

    return list(all_ids)


def read_email(mail, email_id):
    status, msg_data = mail.fetch(email_id, "(RFC822)")

    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    gmail_id = msg.get("Message-ID", "").strip()
    if not gmail_id:
        gmail_id = email_id.decode()  # fallback if header missing

    subject, encoding = decode_header(msg["Subject"])[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding or "utf-8")

    sender = msg.get("From", "")

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore")
    body = clean_body(body)
    return {
        "gmail_id": gmail_id,
        "sender": sender,
        "subject": subject,
        "body": body
    }


def save_email(data):
    if not data.get("gmail_id"):
        return False

    obj, created = GmailEmail.objects.get_or_create(
        gmail_id=data["gmail_id"],
        defaults={
            "sender": data.get("sender", ""),
            "subject": data.get("subject", ""),
            "body": data.get("body", ""),
        }
    )
    return created


def clean_body(body):
    # Remove URLs
    body = re.sub(r'http\S+', '', body)

    # Remove tracking/footer separators
    body = re.sub(r'-{10,}', '', body)

    # Remove "This email was intended for..." footer
    body = re.sub(r'This email was intended for.*', '', body, flags=re.DOTALL)

    # Remove "Unsubscribe", "Help", "©" lines
    body = re.sub(r'(Unsubscribe|Help|©|Learn why we included).*', '', body, flags=re.MULTILINE)

    # Remove excessive whitespace and blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = re.sub(r'[ \t]+', ' ', body)

    return body.strip()
