# mindbaboon.py

import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler


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

# 1. Start APScheduler once, near app startup
def init_scheduler():
    try:
        scheduler.start()
    except Exception as e:
        # If scheduler is already running, just pass
        pass

# 2. Database Helpers
def get_db_connection():
    conn = sqlite3.connect("mindbaboon.db")
    conn.row_factory = sqlite3.Row
    return conn

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
            next_step_description TEXT,
            reward TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
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
        next_step_description = request.form.get("next_step_description", "")
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
                next_step_description,
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
            next_step_description,
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
        next_step_description = request.form["next_step_description"]
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
                next_step_description = ?,
                reward = ?,
                completed = ?
            WHERE id = ?
        """, (
            goal_name,
            goal_description,
            time_span,
            specific_date,
            iteration,
            next_step_description,
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
@app.route("/delete/<int:goal_id>", methods=["POST"])
def delete_goal(goal_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()

    # Remove the reminder job from APScheduler
    remove_reminder(goal_id)

    return redirect(url_for("index"))

# 4. Run the App
if __name__ == "__main__":
    create_tables()  # Create the DB table if missing
    init_scheduler()  # Use the new init function
    app.run(debug=True)
