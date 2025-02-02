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

# Define Prague timezone
TIMEZONE = pytz.timezone('Europe/Prague')

class SchedulerManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_scheduler(cls):
        if cls._instance is None:
            # Use the Docker volume path
            data_dir = '/app/data'
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'mindbaboon.db')
            jobstore_path = f'sqlite:///{db_path}'

            # Configure scheduler with persistent storage
            jobstores = {
                'default': SQLAlchemyJobStore(url=jobstore_path)
            }

            executors = {
                'default': ThreadPoolExecutor(20)
            }

            job_defaults = {
                'coalesce': False,  # Changed to True to prevent duplicate runs
                'max_instances': 1,
                'misfire_grace_time': 3600
            }

            cls._instance = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone=TIMEZONE  # Set Prague timezone
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
    print(f"send goal function is here")
    with SchedulerManager._lock:  
        conn = get_db_connection()
        try:
            # Fetch goal from database
            goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            print(f"DEBUG: Goal data for ID {goal_id}: {goal}")

            if not goal:
                print(f"WARNING: No goal found with ID {goal_id}. Skipping reminder.")
                return

            if goal["completed"] == 1 or goal["is_paused"] == 1:
                print(f"INFO: Goal {goal_id} is either completed or already paused.")
                return

            goal_name = goal["goal_name"]
            next_steps = goal["next_steps"]

            print(f"DEBUG: Attempting to send reminder for goal: '{goal_name}'")

            # Prepare email message
            message = next_steps if next_steps else "Please update the next steps to resume scheduling."
            try:
                send_email(
                    os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"),
                    goal_id,
                    goal_name,
                    message
                )
                print(f"DEBUG: Email sent for goal: '{goal_name}'")

                # Mark goal as paused only after email successfully sends
                conn.execute("UPDATE goals SET is_paused = 1 WHERE id = ?", (goal_id,))
                conn.commit()
            except Exception as email_err:
                print(f"ERROR: Failed to send email for goal '{goal_name}': {email_err}")
                # Ensure the goal is not paused so that the reminder can be retried later
                conn.execute("UPDATE goals SET is_paused = 0 WHERE id = ?", (goal_id,))
                conn.commit()
        except Exception as outer_err:
            print(f"ERROR in send_goal_reminder: {outer_err}")
        finally:
            conn.close()


def schedule_reminder(goal_id, iteration):
    """
    Schedule or update a recurring APScheduler job.
    """
    print(f"schedule reminder function is here")
    interval_args = {
        "week": {"seconds": 30},
        "2 weeks": {"weeks": 2},
        "month": {"weeks": 4},
    }.get(iteration, None)

    if not interval_args:
        print(f"WARNING: Invalid iteration value: {iteration}")
        return

    job_id = f"goal_{goal_id}"
    
    # Remove existing job if it exists
    try:
        scheduler.remove_job(job_id)
    except:
        pass  # Job doesn't exist, that's fine

    # Add new job with Prague timezone
    try:
        now = datetime.now(TIMEZONE)
        job = scheduler.add_job(
            func=send_goal_reminder,
            trigger="interval",
            id=job_id,
            replace_existing=True,
            kwargs={"goal_id": goal_id},
            **interval_args,
            next_run_time=now
        )
        print(f"DEBUG: Successfully scheduled job {job_id}, next run at: {job.next_run_time}")
    except Exception as e:
        print(f"ERROR: Failed to schedule job: {e}")

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
