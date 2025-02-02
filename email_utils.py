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

print(f"DEBUG: Using SMTP Server: {EMAIL_SMTP_SERVER}")
print(f"DEBUG: Using SMTP Port: {EMAIL_SMTP_PORT}")
print(f"DEBUG: Using Email Username: {EMAIL_USERNAME}")
print(f"DEBUG: Using Email Password: {EMAIL_PASSWORD[:4]}******")  # Masked for security

def format_email_content(goal_name, next_steps, goal_id):
    """
    Format the subject and body of the email for a goal with iteration question.
    """
    # Import quotes dynamically from mindbaboon.py
    try:
        from mindbaboon import MOTIVATIONAL_GOALS
        quote = random.choice(MOTIVATIONAL_GOALS)
    except ImportError:
        quote = "Stay motivated and keep pushing forward!"  # Fallback quote

    iteration_url_yes = f"http://127.0.0.1:5000/iteration/{goal_id}?completed=yes"
    iteration_url_no = f"http://127.0.0.1:5000/iteration/{goal_id}?completed=no"

    subject = f"Mindbaboon is watching: {goal_name}"
    body = (
        f"{quote}\n\n"
        f"Goal: {goal_name}\n"
        f"Next Steps: {next_steps}\n\n"
        f"Step completed? [Yes]({iteration_url_yes}) | [No]({iteration_url_no})\n\n"
        f"Keep up the great work!"
    )
    return subject, body



def send_email(to_address, goal_id, goal_name, next_steps):
    """
    Send an email using SMTP.
    """
    subject, body = format_email_content(goal_name, next_steps, goal_id)
    print("DEBUG: Preparing to send email...")

    msg = EmailMessage()
    msg["From"] = EMAIL_USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        print("DEBUG: Connecting to SMTP server...")
        smtp = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        smtp.starttls()

        print("DEBUG: Logging in...")
        smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)

        print("DEBUG: Sending email...")
        smtp.send_message(msg)

        print("✅ DEBUG: Email sent successfully!")
        smtp.quit()
    except Exception as e:
        print(f"DEBUG: Email failed to send. Error: {e}")