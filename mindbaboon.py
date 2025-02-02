# mindbaboon.py
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, request, jsonify
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import os
from database import get_db_connection
from iteration import iteration_bp
import logging
from email_utils import send_email  # Import email utility

# Add after imports
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    logger.addHandler(logging.StreamHandler())

# Predefined list of motivational goals or quotes
MOTIVATIONAL_GOALS = [
    "Push yourself, because no one else is going to do it for you.",
    "Great things never come from comfort zones.",
    "Dream it. Believe it. Build it.",
    "Don't stop until you're proud.",
    "Your limitation—it's only your imagination.",
    "Do something today that your future self will thank you for."
]

# Import the scheduler logic
from scheduler import (
    scheduler,           # The BackgroundScheduler instance
    schedule_reminder,   # Function to add/replace a per-goal job
    remove_reminder      # Function to remove the per-goal job
)

app = Flask(__name__)
app.register_blueprint(iteration_bp)

# 1. Start APScheduler once, near app startup
def init_scheduler():
    """Initialize the APScheduler instance"""
    try:
        logger.debug("Starting scheduler...")
        if not scheduler.running:
            scheduler.start()
            logger.debug("Scheduler started successfully")
        else:
            logger.debug("Scheduler already running")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise


def create_tables():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT NOT NULL,
            goal_description TEXT,
            time_span TEXT,
            end_date TEXT,
            iteration TEXT,
            next_steps TEXT,
            reward TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            is_paused INTEGER NOT NULL DEFAULT 0,
            last_email_sent TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            last_reminder_at TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

    

# 3. Routes

# -- Index (List All Goals) --
@app.route("/")
def index():
    conn = get_db_connection()
    goals = conn.execute("SELECT * FROM goals").fetchall()
    conn.close()
    # Pick a random motivational goal
    random_goal = random.choice(MOTIVATIONAL_GOALS)

    return render_template("index.html", goals=goals, motivational_goal=random_goal)

@app.route("/add", methods=["GET", "POST"])
def add_goal():
    if request.method == "POST":
        goal_name = request.form["goal_name"]
        goal_description = request.form.get("goal_description", "")
        time_span = request.form.get("time_span", "")
        specific_date = request.form.get("specific_date") if time_span == "specific_date" else None
        iteration = request.form.get("iteration", "")
        next_steps = request.form.get("next_steps", "")
        reward = request.form.get("reward", "")

        now = datetime.now()  # For created_at

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO goals (
                goal_name,
                goal_description,
                time_span,
                end_date,
                iteration,
                next_steps,
                reward,
                completed,
                created_at,
                last_reminder_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            goal_name,
            goal_description,
            time_span,
            specific_date,
            iteration,
            next_steps,
            reward,
            0,
            now,
            None
        ))
        conn.commit()

        # Get the auto-generated ID for the new goal
        goal_id = cur.lastrowid
        conn.close()

        # Schedule the reminder for this newly created goal
        schedule_reminder(goal_id, iteration)

        return redirect(url_for("index"))

    return render_template("add.html")


# -- Edit an Existing Goal --
@app.route("/edit/<int:goal_id>", methods=["GET", "POST"])
def edit_goal(goal_id):
    conn = get_db_connection()
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

    if not goal:
        conn.close()
        return "Goal not found.", 404

    if request.method == "POST":
        goal_name = request.form["goal_name"]
        goal_description = request.form["goal_description"]
        time_span = request.form["time_span"]
        specific_date = request.form.get("specific_date") if time_span == "specific_date" else None
        iteration = request.form["iteration"]
        next_steps = request.form["next_steps"]
        reward = request.form["reward"]
        completed = 1 if request.form.get("completed") == "on" else 0

        conn.execute("""
            UPDATE goals
            SET 
                goal_name = ?,
                goal_description = ?,
                time_span = ?,
                end_date = ?,
                iteration = ?,
                next_steps = ?,
                reward = ?,
                completed = ?
            WHERE id = ?
        """, (
            goal_name,
            goal_description,
            time_span,
            specific_date,
            iteration,
            next_steps,
            reward,
            completed,
            goal_id
        ))
        conn.commit()
        conn.close()

        # Reschedule the job if iteration changed (or just always reschedule)
        schedule_reminder(goal_id, iteration)

        return redirect(url_for("index"))

    conn.close()
    return render_template("edit.html", goal=goal)

# -- Delete a Goal --
@app.route('/delete_goal', methods=['POST'])
def delete_goal():
    goal_id = request.form.get('goal_id')

    if not goal_id:
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete history associated with the goal
        cursor.execute("DELETE FROM goal_history WHERE goal_id = ?", (goal_id,))

        # Delete the goal itself
        cursor.execute("DELETE FROM goals WHERE id = ?", (goal_id,))

        conn.commit()
        conn.close()

        # Remove the reminder job from APScheduler
        remove_reminder(goal_id)

    except Exception as e:
        # Optionally log the error for debugging purposes
        print(f"Error occurred: {e}")
    
    # Redirect back to the index page
    return redirect(url_for("index"))

# Send startup email
def send_startup_email():
    """Send a startup notification email."""
    try:
        send_email(os.getenv("DEFAULT_TO_ADDRESS", "example@domain.com"), 0, "Startup Notification", "Hello, World!")
        logger.info("Startup email sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send startup email: {e}")

# 4. Run the App
if __name__ == "__main__":
    create_tables()
    init_scheduler()
    send_startup_email()
    logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', port=5000)
