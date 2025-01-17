from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import sqlite3
import os
from email_utils import send_email  # Import the email utility

# Initialize a global BackgroundScheduler instance
scheduler = BackgroundScheduler()

def get_db_connection():
    """
    Database connection logic.
    """
    conn = sqlite3.connect("mindbaboon.db")
    conn.row_factory = sqlite3.Row
    return conn

def send_goal_reminder(goal_id):
    """
    Called by APScheduler job to send an email reminder for a specific goal.
    """
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

    scheduler.add_job(
        func=send_goal_reminder,
        trigger="interval",
        id=job_id,
        replace_existing=True,
        kwargs={"goal_id": goal_id},
        **interval_args,
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
