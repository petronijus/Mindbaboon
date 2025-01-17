from flask import Blueprint, request, render_template, redirect, url_for
from datetime import datetime
import sqlite3

iteration_bp = Blueprint('iteration', __name__)

def get_db_connection():
    conn = sqlite3.connect("mindbaboon.db")
    conn.row_factory = sqlite3.Row
    return conn

@iteration_bp.route("/iteration/<int:goal_id>", methods=["GET", "POST"])
def iteration_view(goal_id):
    conn = get_db_connection()
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

    if not goal:
        conn.close()
        return "Goal not found", 404

    if request.method == "POST":
        completed = request.form.get("completed")
        description = request.form.get("description", "")
        next_steps = request.form.get("next_steps", goal["next_steps"])
        reward = request.form.get("reward", goal["reward"])
        iteration_frequency = request.form.get("iteration", goal["iteration"])

        # Save step to history
        conn.execute("""
            INSERT INTO goal_history (goal_id, completed, description, next_steps, reward, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (goal_id, completed, description, next_steps, reward, datetime.now()))
        conn.commit()

        # Update the goal with new data and unpause the scheduler
        conn.execute("""
            UPDATE goals
            SET next_steps = ?, reward = ?, iteration = ?, is_paused = 0
            WHERE id = ?
        """, (next_steps, reward, iteration_frequency, goal_id))
        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    conn.close()
    return render_template("iteration.html", goal=goal)
