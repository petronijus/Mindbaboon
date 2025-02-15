from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from flask import render_template
from datetime import datetime, timedelta
import sqlite3
import os
from config import ITERATION_INTERVALS, VERSION
import threading
from database import get_db_connection
import pytz
import logging
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import socket
import random

# Define Prague timezone
TIMEZONE = pytz.timezone('Europe/Prague')


# Set up logger and avoid duplicate handlers
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class SchedulerManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_scheduler(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-check locking pattern
                    data_dir = 'data'
                    os.makedirs(data_dir, exist_ok=True)
                    db_path = os.path.join(data_dir, 'mindbaboon.db')
                    jobstore_path = f'sqlite:///{db_path}'
                    jobstores = {'default': SQLAlchemyJobStore(url=jobstore_path)}
                    executors = {'default': ThreadPoolExecutor(20)}
                    job_defaults = {
                        'coalesce': True,  # Prevent duplicate runs
                        'max_instances': 1,
                        'misfire_grace_time': 3600
                    }
                    cls._instance = BackgroundScheduler(
                        jobstores=jobstores,
                        executors=executors,
                        job_defaults=job_defaults,
                        timezone=TIMEZONE
                    )
        return cls._instance

# Create a single scheduler instance
scheduler = SchedulerManager.get_scheduler()

# Load environment variables and SMTP credentials
load_dotenv()
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Helper: Get host for iteration URLs
def get_server_host():
    host = os.getenv("SERVER_HOST")
    if not host or host == "0.0.0.0":
        try:
            host = socket.gethostbyname(socket.gethostname())
        except Exception:
            host = "localhost"
    return host

def render_email(email_type, context):
    """
    Render an email template based on the email type.
    :param email_type: The name of the template (e.g., "confirmation_email").
    :param context: A dictionary of variables to pass to the template.
    :return: subject, body (HTML content)
    """
    template_name = f"emails/{email_type}.html"
    subject = context.get("subject", "Mindbaboon Notification")
    body = render_template(template_name, **context)
    return subject, body

# Helper: Format email content for iteration messages
def format_email_content(goal_name, next_steps, goal_id):
    try:
        from mindbaboon import MOTIVATIONAL_GOALS
        quote = random.choice(MOTIVATIONAL_GOALS)
    except ImportError:
        quote = "Stay motivated and keep pushing forward!"
    server_host = get_server_host()
    iteration_url_yes = f"http://{server_host}:5000/iteration/{goal_id}?completed=yes"
    iteration_url_no = f"http://{server_host}:5000/iteration/{goal_id}?completed=no"
    subject = f"Mindbaboon is watching: {goal_name}"
    body = (f"{quote}\n\n"
            f"Goal: {goal_name}\n"
            f"Next Steps: {next_steps}\n\n"
            f"Step completed? [Yes]({iteration_url_yes}) | [No]({iteration_url_no})\n\n"
            f"Keep up the great work!")
    return subject, body

# Helper: Generate confirmation email body
def generate_confirmation_email_body(goal_name, next_steps):
    return f"New goal '{goal_name}' has been created successfully. Next steps: {next_steps}"

# Helper: Send email using SMTP
def send_email(email_type, to_address, context):
    """
    Send an email based on the specified email type.
    :param email_type: The template name (without .html) for the email body.
    :param to_address: The recipient's email address.
    :param context: A dictionary of variables to render in the email.
    """
    subject, body = render_email(email_type, context)
    msg = EmailMessage()
    msg["From"] = EMAIL_USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body, subtype='html')  # Set content type to HTML
    try:
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info(f"Email '{email_type}' sent successfully to {to_address}.")
    except Exception as e:
        logger.error(f"Failed to send '{email_type}' email to {to_address}: {e}")

# Helper: Send confirmation email using the confirmation_email template
def send_confirmation_email(goal_id):
    logger.info(f"=== send_confirmation_email START for goal_id: {goal_id} ===")
    conn = get_db_connection()
    try:
        goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not goal:
            logger.warning(f"WARNING: No goal found with ID {goal_id}. Skipping confirmation email.")
            return
        context = {
            "goal_name": goal["goal_name"],
            "next_steps": goal["next_steps"],
            "subject": f"Goal Created: {goal['goal_name']}"
        }
        send_email(
            "confirmation_email", 
            os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"),
            context
        )
        logger.info(f"Confirmation email sent successfully for goal: '{goal['goal_name']}'")
    except Exception as e:
        logger.error(f"Failed to send confirmation email for goal {goal_id}: {e}")
    finally:
        conn.close()
        logger.info(f"=== send_confirmation_email END for goal_id: {goal_id} ===")

def send_goal_reminder(goal_id):
    logger.info(f"=== send_goal_reminder START for goal_id: {goal_id} ===")
    # Add application context to use Flask functionalities
    from mindbaboon import app  # Import here to avoid circular dependency issues
    with app.app_context():
        conn = get_db_connection()
        try:
            goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            if not goal:
                logger.warning(f"No goal found with ID {goal_id}. Skipping reminder.")
                return
            if goal["completed"] == 1 or goal["is_paused"] == 1:
                logger.info(f"Goal {goal_id} is either completed or already paused.")
                return
            context = {
                "goal_name": goal["goal_name"],
                "next_steps": goal["next_steps"],
                "iteration_url_yes": f"http://{get_server_host()}:5000/iteration/{goal_id}?completed=yes",
                "iteration_url_no": f"http://{get_server_host()}:5000/iteration/{goal_id}?completed=no",
                "quote": "Keep pushing forward!"
            }
            send_email("normal_email", os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), context)
            now = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("UPDATE goals SET last_reminder_at = ? WHERE id = ?", (now, goal_id))
            conn.execute("UPDATE goals SET is_paused = 1 WHERE id = ?", (goal_id,))
            conn.commit()
            logger.info(f"Reminder sent for goal: '{goal['goal_name']}'")
        except Exception as e:
            logger.error(f"Error in send_goal_reminder: {e}")
        finally:
            conn.close()
    logger.info(f"=== send_goal_reminder END for goal_id: {goal_id} ===")

def get_next_run_for_goal(goal_id):
    """Fetch the next run time for a specific goal from APScheduler's jobs table."""
    conn = get_db_connection()
    job_id = f"goal_{goal_id}"
    result = conn.execute("SELECT next_run_time FROM apscheduler_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()

    if result and result["next_run_time"]:
        # APScheduler stores next_run_time as a UNIX timestamp (float), convert it to datetime
        return datetime.fromtimestamp(result["next_run_time"], TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
    return None


# Retrieve SMTP credentials from environment variables (for confirmation emails)
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

def schedule_reminder(goal_id, iteration):
    logger.info(f"schedule reminder function is here for goal_id: {goal_id}")
    
    interval_args = ITERATION_INTERVALS.get(iteration)
    if not interval_args:
        logger.warning(f"WARNING: Invalid iteration value: {iteration}")
        return

    job_id = f"goal_{goal_id}"
    existing_job = scheduler.get_job(job_id)
    if (existing_job):
        logger.info(f"DEBUG: Job {job_id} already exists, skipping duplicate scheduling.")
        return
    
    try:
        now = datetime.now(TIMEZONE)
        next_run_time = now + timedelta(**interval_args)

        scheduler.add_job(
            func=send_goal_reminder,
            trigger="interval",
            id=job_id,
            replace_existing=True,
            kwargs={"goal_id": goal_id},
            **interval_args,
            next_run_time=next_run_time
        )
        logger.info(f"DEBUG: Successfully scheduled job {job_id}")

        conn = get_db_connection()
        conn.execute("INSERT INTO iteration_history (iteration_id, status, next_run) VALUES (?, ?, ?)",
                     (goal_id, "Scheduled", next_run_time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.execute("UPDATE goals SET last_reminder_at = ? WHERE id = ?",
                     (now.strftime('%Y-%m-%d %H:%M:%S'), goal_id))
        conn.commit()
        conn.close()

        # Send confirmation email without pausing the goal
        send_confirmation_email(goal_id)
    except Exception as e:
        logger.error(f"ERROR: Failed to schedule job: {e}")

def remove_reminder(goal_id):
    """
    Remove a previously-scheduled job for the given goal_id.
    """
    job_id = f"goal_{goal_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass


def print_next_run_times():
    """
    Print the next run times for all scheduled jobs.
    """
    jobs = scheduler.get_jobs()
    for job in jobs:
        next_run_time = job.next_run_time
        logger.info(f"Job {job.id} next run time: {next_run_time}")
        print(f"WWWWOHHHOOOOOOOO Job {job.id} next run time: {next_run_time}")

def schedule_print_next_run_times():
    """
    Schedule the print_next_run_times function to run periodically.
    """
    scheduler.add_job(
        func=print_next_run_times,
        trigger="interval",
        id="print_next_run_times",
        minutes=1,  # Adjust the interval as needed
        replace_existing=True,
        next_run_time=datetime.now(TIMEZONE)
    )

# Call this function to schedule the periodic printing
schedule_print_next_run_times()

if __name__ == "__main__":
    scheduler.start()
    logger.info("Scheduler started")