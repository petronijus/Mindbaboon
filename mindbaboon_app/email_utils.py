# email_utils.py

import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Retrieve SMTP credentials from environment variables
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

print(f"Loaded email settings: {EMAIL_SMTP_SERVER}, {EMAIL_USERNAME}")


def send_email(to_address, subject, body):
    """
    Send an email using SMTP.
    """
    msg = EmailMessage()
    msg["From"] = EMAIL_USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        smtp.send_message(msg)
