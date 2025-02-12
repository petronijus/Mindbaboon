from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime, timedelta
import sqlite3
import os
from email_utils import send_email, generate_confirmation_email_body  # Removed send_confirmation_email import
from config import ITERATION_INTERVALS, VERSION
import threading
from database import get_db_connection
import pytz
import logging
import smtplib
from email.message import EmailMessage

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

def send_goal_reminder(goal_id):
    """
    Called by APScheduler job to send an email reminder for a specific goal.
    Marks the goal as paused only after the email has been sent.
    If sending fails, it resets is_paused to allow future attempts.
    """
    logger.info(f"=== send_goal_reminder START for goal_id: {goal_id} ===")
    print(f"send goal function is here for goal_id: {goal_id}")
    
    with SchedulerManager._lock:  
        conn = get_db_connection()
        try:
            # Fetch goal from database
            goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            if not goal:
                logger.warning(f"WARNING: No goal found with ID {goal_id}. Skipping reminder.")
                return

            if goal["completed"] == 1 or goal["is_paused"] == 1:
                print(f"INFO: Goal {goal_id} is either completed or already paused.")
                logger.info(f"INFO: Goal {goal_id} is completed.")
                return
            
            # Check if the last email was sent recently (e.g., within 24 hours)
            last_email_sent = goal["last_email_sent"]
            if last_email_sent:
                last_email_sent_time = datetime.strptime(last_email_sent, "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - last_email_sent_time).total_seconds() < 86400:  # 24 hours
                    logger.info(f"INFO: Email already sent within the last 24 hours for goal {goal_id}.")
                    return

            goal_name = goal["goal_name"]
            next_steps = goal["next_steps"]

            logger.info(f"DEBUG: Attempting to send reminder for goal: '{goal_name}'")

            # Prepare email message
            message = next_steps if next_steps else "Please update the next steps to resume scheduling."
            try:
                send_email(
                    os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"),
                    goal_id,
                    goal_name,
                    message
                )
                
                # Update last_reminder_at after a successful email send
                now = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
                conn.execute("UPDATE goals SET last_reminder_at = ? WHERE id = ?", (now, goal_id))
                conn.commit()

                logger.info(f"DEBUG: Email sent for goal: '{goal_name}', last_reminder_at updated to {now}")
        
                # Mark goal as paused only after email successfully sends
                conn.execute("UPDATE goals SET is_paused = 1 WHERE id = ?", (goal_id,))
                conn.commit()
                print(f"DEBUG: Email sent for goal: '{goal_name}'")
                logger.info(f"DEBUG: Email sent for goal: '{goal_name}'")
            except Exception as email_err:
                print(f"ERROR: Failed to send email for goal '{goal_name}': {email_err}")
                # Ensure the goal is not paused so that the reminder can be retried later
                conn.execute("UPDATE goals SET is_paused = 0 WHERE id = ?", (goal_id,))
                conn.commit()
                logger.error(f"ERROR: Failed to send email for goal '{goal_name}': {email_err}")
        except Exception as outer_err:
            logger.error(f"ERROR in send_goal_reminder: {outer_err}")
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

def send_confirmation_email(goal_id):
    """
    Send a confirmation email when a new goal is created.
    Uses inline SMTP logic and takes the body content from email_utils.
    """
    logger.info(f"=== send_confirmation_email START for goal_id: {goal_id} ===")
    conn = get_db_connection()
    try:
        goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not goal:
            logger.warning(f"WARNING: No goal found with ID {goal_id}. Skipping confirmation email.")
            return

        goal_name = goal["goal_name"]
        next_steps = goal["next_steps"]

        logger.info(f"DEBUG: Sending confirmation email for goal: '{goal_name}'")
        subject = f"Goal Created: {goal_name}"
        body = generate_confirmation_email_body(goal_name, next_steps)

        msg = EmailMessage()
        msg["From"] = EMAIL_USERNAME
        msg["To"] = os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com")
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            smtp = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
            smtp.quit()
            logger.info(f"DEBUG: Confirmation email sent for goal: '{goal_name}'")
        except Exception as e:
            logger.error(f"DEBUG: Confirmation email failed to send. Error: {e}")
    except Exception as email_err:
        logger.error(f"ERROR: Failed to send confirmation email for goal '{goal_name}': {email_err}")
    finally:
        conn.close()
        logger.info(f"=== send_confirmation_email END for goal_id: {goal_id} ===")

def schedule_reminder(goal_id, iteration):
    logger.info(f"schedule reminder function is here for goal_id: {goal_id}")
    
    interval_args = ITERATION_INTERVALS.get(iteration)
    if not interval_args:
        logger.warning(f"WARNING: Invalid iteration value: {iteration}")
        return

    job_id = f"goal_{goal_id}"
    existing_job = scheduler.get_job(job_id)
    if existing_job:
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