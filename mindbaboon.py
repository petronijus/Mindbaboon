# mindbaboon.py
import sqlite3
import random
import os
import logging
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from database import (
    get_db_connection,
    get_setting,
    set_setting,
    get_iteration_slot,
    set_iteration_slot,
)
from iteration import iteration_bp
from api import api_bp
from auth import auth_bp, init_oauth, require_login
from scheduler import (
    scheduler,
    schedule_reminder,
    remove_reminder,
    send_startup_email,
    get_next_run_for_goal,
    reschedule_all_active,
)
from config import VERSION, MOTIVATIONAL_QUOTES
from init_mindbaboon_db import initialize_database


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

default_email = get_setting("default_email")
if default_email:
    os.environ["DEFAULT_TO_ADDRESS"] = default_email


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith(("dev-", "changeme")):
        raise RuntimeError(f"{name} must be set to a strong production value")
    return value


app = Flask(__name__)

# Cloudflare Tunnel terminates TLS and forwards via HTTP — without ProxyFix
# Flask sees scheme=http and url_for(_external=True) generates http:// URLs,
# which then mismatch the OAuth redirect_uri registered in GCP.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.secret_key = _require_env("FLASK_SECRET_KEY")
app.config.update(
    SESSION_COOKIE_NAME="__Host-mb_session",  # __Host- prefix requires Secure+Path=/+no Domain
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    WTF_CSRF_TIME_LIMIT=None,  # tie token lifetime to session, not 1h default
)

csrf = CSRFProtect(app)
# API uses X-API-Key auth (CSRF-immune by design). Exempt the whole blueprint.
csrf.exempt(api_bp)

Talisman(
    app,
    force_https=False,  # Cloudflare handles HTTPS upgrade; ProxyFix tells us scheme
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    strict_transport_security_include_subdomains=True,
    strict_transport_security_preload=True,
    frame_options="DENY",
    referrer_policy="strict-origin-when-cross-origin",
    content_security_policy={
        "default-src": "'self'",
        "style-src": ["'self'", "'unsafe-inline'", "https://use.typekit.net"],
        "font-src": ["'self'", "https://use.typekit.net", "https://p.typekit.net"],
        "img-src": ["'self'", "data:"],
        "script-src": "'self'",
        "form-action": "'self' https://accounts.google.com",
        "frame-ancestors": "'none'",
    },
    content_security_policy_nonce_in=None,
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

init_oauth(app)

app.register_blueprint(auth_bp)
app.register_blueprint(iteration_bp)
app.register_blueprint(api_bp)


@app.before_request
def _make_session_permanent():
    session.permanent = True


@app.context_processor
def inject_globals():
    return {
        "current_year": datetime.now().year,
        "version": VERSION,
        "current_user": session.get("user"),
    }


def init_scheduler():
    try:
        if not scheduler.running:
            scheduler.start()
            logger.debug("Scheduler started")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise


@app.route("/")
@require_login
def index():
    message = request.args.get("message")
    conn = get_db_connection()
    goals = conn.execute("""
        SELECT g.*, ih.next_run
        FROM goals g
        LEFT JOIN (
            SELECT iteration_id, MAX(next_run) as next_run
            FROM iteration_history
            GROUP BY iteration_id
        ) ih ON g.id = ih.iteration_id
    """).fetchall()
    conn.close()

    random_quote = random.choice(MOTIVATIONAL_QUOTES)
    goals = [dict(goal) for goal in goals]

    for goal in goals:
        last_reminder_at = goal.get('last_reminder_at')
        next_run = get_next_run_for_goal(goal['id'])
        if last_reminder_at and next_run:
            last_reminder = datetime.strptime(last_reminder_at, '%Y-%m-%d %H:%M:%S')
            next_run_time = datetime.strptime(next_run, '%Y-%m-%d %H:%M:%S')
            total_time = (next_run_time - last_reminder).total_seconds()
            remaining_time = (next_run_time - datetime.now()).total_seconds()
            progress = max(0, min(100, ((total_time - remaining_time) / total_time) * 100))
            goal['progress'] = progress
        else:
            goal['progress'] = 0
        goal['next_run'] = next_run

    return render_template("index.html", goals=goals, motivational_quote=random_quote, message=message, version=VERSION)


@app.route("/add", methods=["GET", "POST"])
@require_login
def add_goal():
    if request.method == "POST":
        goal_name = (request.form.get("goal_name") or "").strip()
        if not goal_name:
            return "goal_name is required", 400
        goal_description = request.form.get("goal_description", "")
        time_span = request.form.get("time_span", "")
        specific_date = request.form.get("specific_date") if time_span == "specific_date" else None
        iteration = request.form.get("iteration", "")
        next_steps = request.form.get("next_steps", "")
        reward = request.form.get("reward", "")

        now = datetime.now()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO goals (
                goal_name, goal_description, time_span, end_date,
                iteration, next_steps, reward, completed, created_at, last_reminder_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (goal_name, goal_description, time_span, specific_date,
              iteration, next_steps, reward, 0, now, None))
        conn.commit()
        goal_id = cur.lastrowid
        conn.close()

        schedule_reminder(goal_id, iteration)
        return redirect(url_for("index"))

    return render_template("add.html", version=VERSION)


@app.route("/edit/<int:goal_id>", methods=["GET", "POST"])
@require_login
def edit_goal(goal_id):
    conn = get_db_connection()
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

    if not goal:
        conn.close()
        return jsonify({"error": "Goal not found"}), 404

    if request.method == "POST":
        goal_name = (request.form.get("goal_name") or "").strip()
        if not goal_name:
            conn.close()
            return "goal_name is required", 400
        goal_description = request.form.get("goal_description", "")
        time_span = request.form.get("time_span", "")
        specific_date = request.form.get("specific_date") if time_span == "specific_date" else None
        iteration = request.form.get("iteration", "")
        next_steps = request.form.get("next_steps", "")
        reward = request.form.get("reward", "")
        completed = 1 if request.form.get("completed") == "on" else 0

        conn.execute("""
            UPDATE goals
            SET goal_name = ?, goal_description = ?, time_span = ?, end_date = ?,
                iteration = ?, next_steps = ?, reward = ?, completed = ?
            WHERE id = ?
        """, (goal_name, goal_description, time_span, specific_date,
              iteration, next_steps, reward, completed, goal_id))
        conn.commit()
        conn.close()

        schedule_reminder(goal_id, iteration)
        return redirect(url_for("index"))

    conn.close()
    return render_template("edit.html", goal=goal, version=VERSION)


@app.route('/delete_goal', methods=['POST'])
@require_login
def delete_goal():
    goal_id = request.form.get('goal_id')
    if not goal_id:
        return redirect(url_for("index"))
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
        conn.close()
        remove_reminder(goal_id)
    except sqlite3.Error as e:
        logger.error(f"DB error deleting goal {goal_id}: {e}")
    return redirect(url_for("index"))


WEEKDAYS = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"),
            (4, "Fri"), (5, "Sat"), (6, "Sun")]


@app.route("/settings", methods=["GET", "POST"], endpoint="settings")
@require_login
def settings_view():
    if request.method == "POST":
        email_address = request.form["email_address"]
        set_setting("default_email", email_address)
        os.environ["DEFAULT_TO_ADDRESS"] = email_address

        old_slot = get_iteration_slot()
        wd = int(request.form.get("iteration_weekday", old_slot["weekday"]))
        hr = int(request.form.get("iteration_hour", old_slot["hour"]))
        mn = int(request.form.get("iteration_minute", old_slot["minute"]))
        set_iteration_slot(weekday=wd, hour=hr, minute=mn)

        msg = "Settings saved."
        if (wd, hr, mn) != (old_slot["weekday"], old_slot["hour"], old_slot["minute"]):
            rescheduled = reschedule_all_active()
            msg = f"Settings saved. Rescheduled {len(rescheduled)} goal(s)."
        return redirect(url_for("index", message=msg))

    current_email = get_setting("default_email") or "example@domain.com"
    return render_template(
        "settings.html",
        current_email=current_email,
        slot=get_iteration_slot(),
        weekdays=WEEKDAYS,
    )


if __name__ == "__main__":
    import socket
    logger.info(f"STARTUP pid={os.getpid()} host={socket.gethostname()} version={VERSION}")
    initialize_database()
    init_scheduler()
    send_startup_email()
    logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', port=5000)
