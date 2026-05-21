from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from flask import render_template
from datetime import datetime, timedelta
import os
import logging
import smtplib
import random
import re
import socket
from email.message import EmailMessage

import pytz
from dotenv import load_dotenv

from config import ITERATION_INTERVALS, VERSION, MOTIVATIONAL_QUOTES
from database import get_db_connection

TIMEZONE = pytz.timezone('Europe/Prague')

# If we sent a reminder for a goal within this window, skip a re-fire — guards
# against container-restart misfire races and any other accidental double-send.
# Safe because the shortest legitimate cadence is 1 week.
REMINDER_IDEMPOTENCY_WINDOW = timedelta(hours=1)

logger = logging.getLogger(__name__)


def _build_scheduler():
    os.makedirs('data', exist_ok=True)
    db_path = os.path.join('data', 'mindbaboon.db')
    return BackgroundScheduler(
        jobstores={'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')},
        executors={'default': ThreadPoolExecutor(20)},
        job_defaults={'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 60},
        timezone=TIMEZONE,
    )


scheduler = _build_scheduler()

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


def _fmt_day(dt):
    """Pretty short date like 'Saturday 3. May'. No year, no time."""
    if dt is None:
        return None
    return f"{dt.strftime('%A')} {dt.day}. {dt.strftime('%B')}"


def _base_url():
    return f"http://{get_server_host()}:5000"


def _other_active_goals(exclude_id):
    """List other active (not completed) goals with their next_run ISO and pretty date."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, goal_name, next_steps, iteration FROM goals "
            "WHERE id != ? AND completed = 0 ORDER BY id",
            (exclude_id,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        job = scheduler.get_job(f"goal_{r['id']}")
        nxt = job.next_run_time if job else None
        out.append({
            "id": r["id"],
            "goal_name": r["goal_name"],
            "next_steps": r["next_steps"],
            "iteration": r["iteration"],
            "next_day": _fmt_day(nxt),
            "edit_url": f"{_base_url()}/edit/{r['id']}",
        })
    return out


def render_email(email_type, context):
    template_name = f"emails/{email_type}.html"
    subject = context.get("subject", None)
    body = render_template(template_name, **context)
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
        job = scheduler.get_job(f"goal_{goal_id}")
        first_run = job.next_run_time if job else None
        context = {
            "goal_id": goal_id,
            "goal_name": goal["goal_name"],
            "next_steps": goal["next_steps"],
            "quote": random.choice(MOTIVATIONAL_QUOTES),
            "version": VERSION,
            "next_day": _fmt_day(first_run),
            "home_url": _base_url(),
            "edit_url": f"{_base_url()}/edit/{goal_id}",
            "other_goals": _other_active_goals(goal_id),
        }
        send_email("confirmation_email", os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), context)
        logger.info(f"Confirmation email sent for goal: '{goal['goal_name']}'")
    except Exception as e:
        logger.error(f"Failed to send confirmation email for goal {goal_id}: {e}")
    finally:
        conn.close()
        logger.info(f"=== send_confirmation_email END for goal_id: {goal_id} ===")


# If a startup email was sent within this window, don't send another. Catches
# the case where two app processes start nearly simultaneously (multiple
# containers/replicas pointing at the same DB).
STARTUP_EMAIL_DEDUPE_WINDOW = timedelta(minutes=5)


def send_startup_email():
    from mindbaboon import app  # Avoid circular dependency
    from database import get_setting, set_setting
    with app.app_context():
        last = get_setting("last_startup_email_at")
        if last:
            try:
                last_dt = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
                if datetime.now() - last_dt < STARTUP_EMAIL_DEDUPE_WINDOW:
                    logger.warning(
                        f"Skipping startup email — another instance sent one at {last} "
                        f"(within {STARTUP_EMAIL_DEDUPE_WINDOW}). "
                        f"This typically means two app processes are running against the same DB."
                    )
                    return
            except ValueError:
                pass
        context = {
            "welcome_message": "Welcome to Mindbaboon!",
            "info": "Your system has started successfully.",
            "quote": random.choice(MOTIVATIONAL_QUOTES),
            "version": VERSION,
            "home_url": _base_url(),
        }
        send_email("startup_email", os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), context)
        set_setting("last_startup_email_at", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


def _recently_sent(last_email_sent_str):
    """True if last_email_sent_str timestamp is within the idempotency window."""
    if not last_email_sent_str:
        return False
    try:
        last = datetime.strptime(last_email_sent_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return False
    return datetime.now() - last < REMINDER_IDEMPOTENCY_WINDOW


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
            if goal["completed"] == 1 or goal["is_silenced"] == 1:
                logger.info(f"Goal {goal_id} is completed or silenced.")
                return
            # Idempotency: skip if a reminder went out within the last hour.
            if _recently_sent(goal["last_email_sent"]):
                logger.warning(
                    f"Skipping reminder for goal {goal_id}: last_email_sent "
                    f"{goal['last_email_sent']} is within idempotency window."
                )
                return
            interval_args = ITERATION_INTERVALS.get(goal["iteration"]) or {}
            next_check = datetime.now(TIMEZONE) + timedelta(**interval_args) if interval_args else None
            context = {
                "goal_id": goal_id,
                "goal_name": goal["goal_name"],
                "next_steps": goal["next_steps"],
                "iteration_url_yes": f"{_base_url()}/iteration/{goal_id}?completed=yes",
                "iteration_url_no": f"{_base_url()}/iteration/{goal_id}?completed=no",
                "edit_url": f"{_base_url()}/edit/{goal_id}",
                "home_url": _base_url(),
                "quote": random.choice(MOTIVATIONAL_QUOTES),
                "version": VERSION,
                "iteration": goal["iteration"],
                "next_day": _fmt_day(next_check),
                "other_goals": _other_active_goals(goal_id),
            }
            send_email("normal_email", os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), context)
            now_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                "UPDATE goals SET last_reminder_at = ?, last_email_sent = ?, is_silenced = 1 "
                "WHERE id = ?",
                (now_str, now_str, goal_id),
            )
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


def next_iteration_slot(after=None):
    """Next occurrence of the globally-configured iteration window (weekday+time) strictly after `after`."""
    from database import get_iteration_slot
    slot = get_iteration_slot()
    after = after or datetime.now(TIMEZONE)
    candidate = after.replace(hour=slot["hour"], minute=slot["minute"], second=0, microsecond=0)
    days_ahead = (slot["weekday"] - after.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= after:
        candidate += timedelta(days=7)
    return candidate


def schedule_reminder(goal_id, iteration, send_confirmation=True):
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
        next_run_time = next_iteration_slot(after=now)
        scheduler.add_job(
            func=send_goal_reminder,
            trigger="interval",
            id=job_id,
            replace_existing=True,
            kwargs={"goal_id": goal_id},
            **interval_args,
            next_run_time=next_run_time
        )
        logger.info(f"Job {job_id} scheduled at {next_run_time.isoformat()}")
        conn = get_db_connection()
        conn.execute("INSERT INTO iteration_history (iteration_id, status, next_run) VALUES (?, ?, ?)",
                     (goal_id, "Scheduled", next_run_time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.execute("UPDATE goals SET last_reminder_at = ? WHERE id = ?",
                     (now.strftime('%Y-%m-%d %H:%M:%S'), goal_id))
        conn.commit()
        conn.close()
        if send_confirmation:
            send_confirmation_email(goal_id)
    except Exception as e:
        logger.error(f"Failed to schedule job {job_id}: {e}")


def reschedule_all_active():
    """Remove and re-add jobs for every active goal using the current slot + intervals.
    Returns a list of (goal_id, next_run_time ISO) tuples."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, iteration FROM goals WHERE completed = 0 AND iteration != ''"
        ).fetchall()
    finally:
        conn.close()
    results = []
    for row in rows:
        gid, it = row["id"], row["iteration"]
        remove_reminder(gid)
        schedule_reminder(gid, it, send_confirmation=False)
        job = scheduler.get_job(f"goal_{gid}")
        results.append((gid, job.next_run_time.isoformat() if job else None))
    return results


def remove_reminder(goal_id):
    from apscheduler.jobstores.base import JobLookupError
    job_id = f"goal_{goal_id}"
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass


if __name__ == "__main__":
    scheduler.start()
    logger.info("Scheduler started")
