# email_utils.py

import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os
import random

# Load environment variables from .env
load_dotenv()

# Retrieve SMTP credentials from environment variables
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

print(f"Loaded email settings: {EMAIL_SMTP_SERVER}, {EMAIL_USERNAME}")

def format_email_content(goal_name, iteration):
    """
    Format the subject and body of the email for a goal.
    """
    # Import quotes dynamically from mindbaboon.py
    try:
        from mindbaboon import MOTIVATIONAL_GOALS
        quote = random.choice(MOTIVATIONAL_GOALS)
    except ImportError:
        quote = "Stay motivated and keep pushing forward!"  # Fallback quote

    subject = f"Mindbaboon is watching: {goal_name}"
    body = (
        f"{quote}\n\n"
        f"Goal: {goal_name}\n"
        f"Iteration: {iteration}\n\n"
        f"Keep up the great work!"
    )
    return subject, body

def send_email(to_address, goal_name, iteration):
    """
    Send an email using SMTP.
    """
    subject, body = format_email_content(goal_name, iteration)

    msg = EmailMessage()
    msg["From"] = EMAIL_USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        smtp.send_message(msg)
