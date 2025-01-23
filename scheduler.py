from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime
import sqlite3
import os
from email_utils import send_email  # Import the email utility
import threading

class SchedulerManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_scheduler(cls):
        if cls._instance is None:
            # Use the same database as the main application
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
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
                'coalesce': True,  # Changed to True to prevent duplicate runs
                'max_instances': 1,
                'misfire_grace_time': 3600
            }

            cls._instance = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults
            )

            if not cls._instance.running:
                cls._instance.start()

        return cls._instance

# Create a single scheduler instance
scheduler = SchedulerManager.get_scheduler()

def get_db_connection():
    """Database connection with path to data directory"""
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'mindbaboon.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def send_goal_reminder(goal_id):
    """
    Called by APScheduler job to send an email reminder for a specific goal.
    """
    with SchedulerManager._lock:  # Use lock to prevent concurrent execution
        conn = get_db_connection()
        goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

        if not goal or goal["completed"] == 1 or goal["is_paused"] == 1:
            conn.close()
            return

        goal_name = goal["goal_name"]
        next_steps = goal["next_steps"]

        print(f"Sending reminder for goal: '{goal_name}'")

        # Pause the scheduler immediately to prevent further emails
        conn.execute("UPDATE goals SET is_paused = 1 WHERE id = ?", (goal_id,))
        conn.commit()

        # Send the email using the email utility
        try:
            if not next_steps:
                message = "Please update the next steps to resume scheduling."
            else:
                message = next_steps

            send_email(
                os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"),
                goal_id,
                goal_name,
                message
            )

            print(f"Email sent to {os.getenv('DEFAULT_TO_ADDRESS', 'example@domain.com')} for goal: '{goal_name}'")
        except Exception as e:
            print(f"Error sending email: {e}")

        conn.close()

def schedule_reminder(goal_id, iteration):
    """
    Schedule or update a recurring APScheduler job.
    """
    interval_args = {
        "week": {"seconds": 30},
        "2 weeks": {"weeks": 2},
        "month": {"weeks": 4},
    }.get(iteration, None)

    if not interval_args:
        return

    job_id = f"goal_{goal_id}"
    
    # Remove existing job if it exists
    try:
        scheduler.remove_job(job_id)
    except:
        pass  # Job doesn't exist, that's fine

    # Add new job
    scheduler.add_job(
        func=send_goal_reminder,
        trigger="interval",
        id=job_id,
        replace_existing=True,
        kwargs={"goal_id": goal_id},
        **interval_args,
        next_run_time=datetime.now()
    )

def remove_reminder(goal_id):
    """
    Remove a previously-scheduled job for the given goal_id.
    """
    job_id = f"goal_{goal_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
