# scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import sqlite3
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Retrieve SMTP credentials and other configurations from environment variables
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
DEFAULT_TO_ADDRESS = os.getenv("DEFAULT_TO_ADDRESS", "you@example.com")

# Initialize a global BackgroundScheduler instance
scheduler = BackgroundScheduler()

def get_db_connection():
    """ Replicate your DB connection logic here or import from mindbaboon.py. """
    conn = sqlite3.connect("mindbaboon.db")
    conn.row_factory = sqlite3.Row
    return conn

def send_email(to_address, subject, body):

    """ Send an email using SMTP. """
    msg = EmailMessage()
    msg["From"] = EMAIL_USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        smtp.send_message(msg)

def send_goal_reminder(goal_id):
    """
    Called by APScheduler job to send an email reminder for a specific goal.
    """
    conn = get_db_connection()
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    conn.close()

    # If the goal doesn't exist or is completed, do nothing
    if not goal or goal["completed"] == 1:
        return

    goal_name = goal["goal_name"]
    iteration = goal["iteration"]

    subject = f"Mindbaboon Reminder: {goal_name}"
    body = (
        f"Hello,\n\n"
        f"This is your {iteration} reminder for the goal: {goal_name}.\n"
        f"Keep going!\n\n"
        f"Your Mindbaboon"
    )

    # In production, you’d either have a user email or some config
    send_email(DEFAULT_TO_ADDRESS, subject, body)

def schedule_reminder(goal_id, iteration):
    """
    Create (or update) a recurring APScheduler job for this goal_id
    based on the iteration (week, 2 weeks, month).
    """
    # Convert iteration to an interval
    if iteration == "week":
        interval_args = {"seconds": 30}  # For testing, use seconds. Replace with {"weeks": 1} in production.
    elif iteration == "2 weeks":
        interval_args = {"weeks": 2}
    elif iteration == "month":
        interval_args = {"days": 30}
    else:
        # If iteration is invalid, do nothing
        return

    job_id = f"goal_{goal_id}"

    # Create or replace an existing job with the same ID
    scheduler.add_job(
        func=send_goal_reminder,
        trigger="interval",
        id=job_id,
        replace_existing=True,
        kwargs={"goal_id": goal_id},
        **interval_args
    )

def remove_reminder(goal_id):
    """
    Remove a previously-scheduled job for the given goal_id.
    """
    job_id = f"goal_{goal_id}"
    try:
        scheduler.remove_job(job_id)
    except:
        # The job might not exist or has already been removed
        pass
