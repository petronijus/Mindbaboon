from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime
import sqlite3
import os
from email_utils import send_email  # Import the email utility
import threading
from database import get_db_connection
import pytz
import logging

# Define Prague timezone
TIMEZONE = pytz.timezone('Europe/Prague')

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Prevent multiple log handlers
if not logger.hasHandlers():
    handler = logging.StreamHandler()
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

def schedule_reminder(goal_id, iteration):
    """
    Schedule or update a recurring APScheduler job.
    """
    logger.info(f"schedule reminder function is here for goal_id: {goal_id}")
    
    interval_args = {
        "week": {"seconds": 30},
        "2 weeks": {"weeks": 2},
        "month": {"weeks": 4},
    }.get(iteration, None)

    if not interval_args:
        logger.warning(f"WARNING: Invalid iteration value: {iteration}")
        return

    job_id = f"goal_{goal_id}"
    existing_job = scheduler.get_job(job_id)
    if existing_job:
        logger.info(f"DEBUG: Job {job_id} already exists, skipping duplicate scheduling.")
        return
    
    # Add new job with Prague timezone
    try:
        now = datetime.now(TIMEZONE)
        scheduler.add_job(
            func=send_goal_reminder,
            trigger="interval",
            id=job_id,
            replace_existing=True,
            kwargs={"goal_id": goal_id},
            **interval_args,
            next_run_time=now
        )
        logger.info(f"DEBUG: Successfully scheduled job {job_id}")
    except Exception as e:
        logger.error(f"ERROR: Failed to schedule job: {e}")


def remove_reminder(goal_id):
    """
    Remove a previously-scheduled job for the given goal_id.
    """
    print(f"remove reminder function is here")
    job_id = f"goal_{goal_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
