from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from flask import render_template
from datetime import datetime, timedelta
import os
from config import ITERATION_INTERVALS
import threading
from database import get_db_connection
import pytz
import logging
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import socket
import random
import re  # new import for regex
from config import ITERATION_INTERVALS, VERSION, MOTIVATIONAL_QUOTES

# Define Prague timezone
TIMEZONE = pytz.timezone('Europe/Prague')

# Set up logger
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# SchedulerManager using double-check locking
class SchedulerManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_scheduler(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    os.makedirs('data', exist_ok=True)
                    db_path = os.path.join('data', 'mindbaboon.db')
                    jobstore_path = f'sqlite:///{db_path}'
                    jobstores = {'default': SQLAlchemyJobStore(url=jobstore_path)}
                    executors = {'default': ThreadPoolExecutor(20)}
                    job_defaults = {'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 3600}
                    cls._instance = BackgroundScheduler(
                        jobstores=jobstores,
                        executors=executors,
                        job_defaults=job_defaults,
                        timezone=TIMEZONE
                    )
        return cls._instance

scheduler = SchedulerManager.get_scheduler()

# Load environment variables once
load_dotenv()
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

def get_server_host():
    host = os.getenv("SERVER_HOST")
    if not host or host == "0.0.0.0":
        try:
            host = socket.gethostbyname(socket.gethostname())
        except Exception:
            host = "localhost"
    return host

def render_email(email_type, context):
    template_name = f"emails/{email_type}.html"
    # Use subject from context if provided, else set default value.
    subject = context.get("subject", None)
    body = render_template(template_name, **context)
    # If subject is not provided, try to extract from <title> tag in the template.
    if subject is None:
        match = re.search(r'<title>\s*(.*?)\s*</title>', body, re.IGNORECASE | re.DOTALL)
        subject = match.group(1) if match else "Mindbaboon Notification"
    return subject, body

def send_email(email_type, to_address, context):
    subject, body = render_email(email_type, context)
    msg = EmailMessage()
    msg["From"] = EMAIL_USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body, subtype='html')
    try:
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info(f"Email '{email_type}' sent successfully to {to_address}.")
    except Exception as e:
        logger.error(f"Failed to send '{email_type}' email to {to_address}: {e}")

def send_confirmation_email(goal_id):
    logger.info(f"=== send_confirmation_email START for goal_id: {goal_id} ===")
    conn = get_db_connection()
    try:
        goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not goal:
            logger.warning(f"No goal found with ID {goal_id}.")
            return
        context = {
            "goal_name": goal["goal_name"],
            "next_steps": goal["next_steps"],
            "quote": random.choice(MOTIVATIONAL_QUOTES)  # Updated to use dynamic quote
        }
        send_email("confirmation_email", os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), context)
        logger.info(f"Confirmation email sent for goal: '{goal['goal_name']}'")
    except Exception as e:
        logger.error(f"Failed to send confirmation email for goal {goal_id}: {e}")
    finally:
        conn.close()
        logger.info(f"=== send_confirmation_email END for goal_id: {goal_id} ===")

def send_startup_email():
    """New function to send a startup email using the email template's title for subject."""
    from mindbaboon import app  # Avoid circular dependency
    with app.app_context():
        context = {
            "welcome_message": "Welcome to Mindbaboon!",
            "info": "Your system has started successfully.",
            "quote": random.choice(MOTIVATIONAL_QUOTES)  # Updated to use dynamic quote
        }
        send_email("startup_email", os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), context)

def send_goal_reminder(goal_id):
    logger.info(f"=== send_goal_reminder START for goal_id: {goal_id} ===")
    from mindbaboon import app  # Avoid circular dependency
    with app.app_context():
        conn = get_db_connection()
        try:
            goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            if not goal:
                logger.warning(f"No goal found with ID {goal_id}.")
                return
            if goal["completed"] == 1 or goal["is_paused"] == 1:
                logger.info(f"Goal {goal_id} is completed or paused.")
                return
            context = {
                "goal_name": goal["goal_name"],
                "next_steps": goal["next_steps"],
                "iteration_url_yes": f"http://{get_server_host()}:5000/iteration/{goal_id}?completed=yes",
                "iteration_url_no": f"http://{get_server_host()}:5000/iteration/{goal_id}?completed=no",
                "quote": random.choice(MOTIVATIONAL_QUOTES)  # Updated to use dynamic quote
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
    conn = get_db_connection()
    job_id = f"goal_{goal_id}"
    result = conn.execute("SELECT next_run_time FROM apscheduler_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if result and result["next_run_time"]:
        return datetime.fromtimestamp(result["next_run_time"], TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
    return None

def schedule_reminder(goal_id, iteration):
    logger.info(f"Scheduling reminder for goal_id: {goal_id}")
    interval_args = ITERATION_INTERVALS.get(iteration)
    if not interval_args:
        logger.warning(f"Invalid iteration value: {iteration}")
        return

    job_id = f"goal_{goal_id}"
    if scheduler.get_job(job_id):
        logger.info(f"Job {job_id} already exists, skipping scheduling.")
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
        logger.info(f"Job {job_id} scheduled successfully.")
        conn = get_db_connection()
        conn.execute("INSERT INTO iteration_history (iteration_id, status, next_run) VALUES (?, ?, ?)",
                     (goal_id, "Scheduled", next_run_time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.execute("UPDATE goals SET last_reminder_at = ? WHERE id = ?",
                     (now.strftime('%Y-%m-%d %H:%M:%S'), goal_id))
        conn.commit()
        conn.close()
        send_confirmation_email(goal_id)
    except Exception as e:
        logger.error(f"Failed to schedule job {job_id}: {e}")

def remove_reminder(goal_id):
    from apscheduler.jobstores.base import JobLookupError
    job_id = f"goal_{goal_id}"
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass

def print_next_run_times():
    for job in scheduler.get_jobs():
        logger.info(f"Job {job.id} next run time: {job.next_run_time}")

def schedule_print_next_run_times():
    scheduler.add_job(
        func=print_next_run_times,
        trigger="interval",
        id="print_next_run_times",
        minutes=1,
        replace_existing=True,
        next_run_time=datetime.now(TIMEZONE)
    )

# Schedule periodic printing of next run times
schedule_print_next_run_times()

if __name__ == "__main__":
    scheduler.start()
    logger.info("Scheduler started")