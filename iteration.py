from config import ITERATION_INTERVALS, VERSION
from flask import Blueprint, request, render_template, redirect, url_for, jsonify
from datetime import datetime, timedelta
from database import get_db_connection
import pytz
import logging

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone('Europe/Prague')

iteration_bp = Blueprint('iteration', __name__)


@iteration_bp.route("/iteration/<int:goal_id>", methods=["GET", "POST"])
def iteration_view(goal_id):
    conn = get_db_connection()
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()

    if not goal:
        conn.close()
        return "Goal not found", 404

    if request.method == "POST":
        completed = request.form.get("completed", "")     # "yes" / "no" — iteration status
        was_done = request.form.get("was_done", "")
        next_steps = request.form.get("next_steps", goal["next_steps"])
        reward = request.form.get("reward", goal["reward"])

        # Informational only — APScheduler's interval trigger is the source of
        # truth for when the next reminder fires; we just record what we'd
        # expect for history purposes.
        interval_args = ITERATION_INTERVALS.get(goal["iteration"]) or {"minutes": 2}
        next_run = datetime.now(TIMEZONE) + timedelta(**interval_args)

        conn.execute("""
            INSERT INTO iteration_history (iteration_id, status, next_run, updated_at)
            VALUES (?, ?, ?, ?)
        """, (goal_id, completed, next_run.strftime('%Y-%m-%d %H:%M:%S'), datetime.now(TIMEZONE)))

        # User responded → clear the silenced flag so the next scheduled tick
        # can email again. Do NOT touch goals.completed here — that field
        # tracks whether the whole goal is finished, set only via the edit
        # form or the API /complete endpoint.
        conn.execute("""
            UPDATE goals
            SET next_steps = ?, reward = ?, is_silenced = 0
            WHERE id = ?
        """, (next_steps, reward, goal_id))

        conn.execute("""
            INSERT INTO goal_history (goal_id, completed, was_done, next_steps, reward, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (goal_id, completed, was_done, next_steps, reward, datetime.now(TIMEZONE)))

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template("iteration.html", goal=goal, version=VERSION)


@iteration_bp.route('/iteration/<int:iteration_id>/history', methods=['GET'])
def get_iteration_history(iteration_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT status, updated_at FROM iteration_history
        WHERE iteration_id = ?
        ORDER BY updated_at DESC;
    ''', (iteration_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@iteration_bp.route('/goal/<int:goal_id>/history', methods=['GET'])
def get_goal_history(goal_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT completed, was_done, next_steps, reward, timestamp
        FROM goal_history
        WHERE goal_id = ?
        ORDER BY timestamp DESC;
    ''', (goal_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@iteration_bp.route('/iteration/<int:iteration_id>/status', methods=['POST'])
def update_iteration_status(iteration_id):
    data = request.json
    status = data.get("status")

    if status not in ["Yes", "No"]:
        return jsonify({"error": "Invalid status value."}), 400

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO iteration_history (iteration_id, status)
        VALUES (?, ?);
    ''', (iteration_id, status))
    conn.commit()
    conn.close()

    return jsonify({"message": "Status updated successfully."})
