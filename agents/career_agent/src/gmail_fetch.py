import imaplib
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Gmail address and App Password come from .env (never written in code)
load_dotenv()
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

# Same folder that job_emails.py reads
EMAIL_DIR = Path(__file__).resolve().parents[1] / "data" / "job_emails"

# Only LinkedIn job alerts are needed
LINKEDIN_SENDER = "jobalerts-noreply@linkedin.com"


def fetch_linkedin_alerts(days=3):
    """Download LinkedIn job-alert emails from the last few days as .eml files."""
    EMAIL_DIR.mkdir(parents=True, exist_ok=True)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    saved = 0
    with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX", readonly=True)  # read only: nothing is changed in Gmail
        # UID = permanent id of an email (does not change when others are deleted)
        _, data = mail.uid("search", None, f'(FROM "{LINKEDIN_SENDER}" SINCE {since})')
        for num in data[0].split():
            path = EMAIL_DIR / f"linkedin_{num.decode()}.eml"
            if path.exists():
                continue  # already downloaded
            _, msg_data = mail.uid("fetch", num, "(RFC822)")
            path.write_bytes(msg_data[0][1])
            saved += 1
    return saved


if __name__ == "__main__":
    print("New LinkedIn emails saved:", fetch_linkedin_alerts())