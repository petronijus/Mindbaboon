from config import ITERATION_INTERVALS, VERSION
from flask import Blueprint, request, render_template, redirect, url_for, jsonify
from datetime import datetime, timedelta
import sqlite3
import os
from database import get_db_connection
import pytz
import logging
from config import ITERATION_INTERVALS, VERSION

# Set up logger and avoid duplicate handlers
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Define Prague timezone at the top
TIMEZONE = pytz.timezone('Europe/Prague')

iteration_bp = Blueprint('iteration', __name__)



# Existing route for iteration view
@iteration_bp.route("/iteration/<int:goal_id>", methods=["GET", "POST"])
def iteration_view(goal_id):
    conn = get_db_connection()
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

    if not goal:
        conn.close()
        return "Goal not found", 404

    if request.method == "POST":
        completed = request.form.get("completed")  # Iteration-specific
        was_done = request.form.get("was_done", "")  # Goal-specific
        next_steps = request.form.get("next_steps", goal["next_steps"])  # Goal-specific
        reward = request.form.get("reward", goal["reward"])  # Goal-specific
        
        # Calculate the next_run using ITERATION_INTERVALS
        interval_args = ITERATION_INTERVALS.get(goal["iteration"])
        next_run_minutes = interval_args["minutes"] if interval_args else 2  # Default to 2 minutes
        next_run = datetime.now(TIMEZONE) + timedelta(minutes=next_run_minutes)
        

        conn.execute("""
            INSERT INTO iteration_history (iteration_id, status, next_run, updated_at)
            VALUES (?, ?, ?, ?)
        """, (goal_id, completed, next_run.strftime('%Y-%m-%d %H:%M:%S'), datetime.now(TIMEZONE)))

        


        # Update goal-specific fields in goals table
        conn.execute("""
            UPDATE goals
            SET next_steps = ?, reward = ?, completed = ?, is_paused = 0
            WHERE id = ?
        """, (next_steps, reward, completed, goal_id))

        # Save other changes to goal_history
        conn.execute("""
            INSERT INTO goal_history (goal_id, completed, was_done, next_steps, reward, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (goal_id, completed, was_done, next_steps, reward, datetime.now(TIMEZONE)))

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template("iteration.html", goal=goal, version=VERSION)  # Updated line to pass version

@iteration_bp.route('/iteration/<int:iteration_id>/history', methods=['GET'])
def get_iteration_history(iteration_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT status, updated_at FROM iteration_history
        WHERE iteration_id = ?
        ORDER BY updated_at DESC;
    ''', (iteration_id,))
    rows = cursor.fetchall()  # Fetch rows as Row objects

    # Convert each Row to a dictionary
    history = [dict(row) for row in rows]

    conn.close()
    return jsonify(history)  # Now JSON serializable

@iteration_bp.route('/goal/<int:goal_id>/history', methods=['GET'])
def get_goal_history(goal_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT completed, was_done, next_steps, reward, timestamp
        FROM goal_history
        WHERE goal_id = ?
        ORDER BY timestamp DESC;
    ''', (goal_id,))
    rows = cursor.fetchall()  # Fetch rows as Row objects

    # Convert each Row to a dictionary
    history = [dict(row) for row in rows]

    conn.close()
    return jsonify(history)  # Return JSON serializable data


@iteration_bp.route('/iteration/<int:iteration_id>/status', methods=['POST'])
def update_iteration_status(iteration_id):
    """
    Update the status of an iteration and record it in the history.
    """
    data = request.json
    status = data.get("status")  # "Yes" or "No"

    if status not in ["Yes", "No"]:
        return jsonify({"error": "Invalid status value."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert into iteration_history
    cursor.execute('''
        INSERT INTO iteration_history (iteration_id, status)
        VALUES (?, ?);
    ''', (iteration_id, status))

    conn.commit()
    conn.close()

    return jsonify({"message": "Status updated successfully."})

