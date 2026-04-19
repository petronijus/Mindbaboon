"""REST API for Mindbaboon.

All endpoints require an API key in the `X-API-Key` header matching the
`MINDBABOON_API_KEY` environment variable. Returns JSON only.
"""
from functools import wraps
from datetime import datetime
import os
import secrets
import logging

from flask import Blueprint, request, jsonify

from database import (
    get_db_connection,
    get_iteration_slot,
    set_iteration_slot,
    get_setting,
    set_setting,
)
from config import ITERATION_INTERVALS, VERSION
from scheduler import (
    scheduler,
    schedule_reminder,
    remove_reminder,
    get_next_run_for_goal,
    reschedule_all_active,
)

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

VALID_ITERATIONS = set(ITERATION_INTERVALS.keys())


def require_api_key(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = os.getenv("MINDBABOON_API_KEY")
        if not expected:
            return jsonify({"error": "API disabled: MINDBABOON_API_KEY not set"}), 503
        provided = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(provided, expected):
            return jsonify({"error": "Unauthorized"}), 401
        return view(*args, **kwargs)
    return wrapper


def goal_to_dict(row):
    d = dict(row)
    d["next_run"] = get_next_run_for_goal(d["id"])
    return d


@api_bp.route("/health", methods=["GET"])
def health():
    conn = get_db_connection()
    try:
        goal_count = conn.execute("SELECT COUNT(*) AS c FROM goals").fetchone()["c"]
        active_count = conn.execute(
            "SELECT COUNT(*) AS c FROM goals WHERE completed = 0"
        ).fetchone()["c"]
        job_rows = conn.execute(
            "SELECT id, next_run_time FROM apscheduler_jobs ORDER BY next_run_time ASC"
        ).fetchall()
    finally:
        conn.close()

    jobs = [
        {
            "id": r["id"],
            "next_run_time": datetime.fromtimestamp(r["next_run_time"]).isoformat()
            if r["next_run_time"]
            else None,
        }
        for r in job_rows
    ]
    return jsonify(
        {
            "status": "ok",
            "version": VERSION,
            "scheduler_running": scheduler.running,
            "goals_total": goal_count,
            "goals_active": active_count,
            "scheduled_jobs": len(jobs),
            "jobs": jobs,
            "valid_iterations": sorted(VALID_ITERATIONS),
        }
    )


@api_bp.route("/goals", methods=["GET"])
@require_api_key
def list_goals():
    include_completed = request.args.get("include_completed", "false").lower() == "true"
    conn = get_db_connection()
    try:
        if include_completed:
            rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM goals WHERE completed = 0 ORDER BY created_at DESC"
            ).fetchall()
    finally:
        conn.close()
    return jsonify([goal_to_dict(r) for r in rows])


@api_bp.route("/goals/<int:goal_id>", methods=["GET"])
@require_api_key
def get_goal(goal_id):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal_to_dict(row))


@api_bp.route("/goals", methods=["POST"])
@require_api_key
def create_goal():
    data = request.get_json(silent=True) or {}
    goal_name = (data.get("goal_name") or "").strip()
    if not goal_name:
        return jsonify({"error": "goal_name is required"}), 400

    iteration = data.get("iteration") or ""
    if iteration and iteration not in VALID_ITERATIONS:
        return jsonify(
            {"error": f"invalid iteration; must be one of {sorted(VALID_ITERATIONS)}"}
        ), 400

    goal_description = data.get("goal_description", "")
    time_span = data.get("time_span", "")
    end_date = data.get("end_date") if time_span == "specific_date" else None
    next_steps = data.get("next_steps", "")
    reward = data.get("reward", "")

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO goals (
                goal_name, goal_description, time_span, end_date,
                iteration, next_steps, reward, completed, created_at, last_reminder_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, NULL)
            """,
            (
                goal_name,
                goal_description,
                time_span,
                end_date,
                iteration,
                next_steps,
                reward,
                datetime.now(),
            ),
        )
        conn.commit()
        goal_id = cur.lastrowid
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    finally:
        conn.close()

    if iteration:
        schedule_reminder(goal_id, iteration)

    return jsonify(goal_to_dict(row)), 201


@api_bp.route("/goals/<int:goal_id>", methods=["PATCH"])
@require_api_key
def update_goal(goal_id):
    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return jsonify({"error": "Goal not found"}), 404

        allowed = {
            "goal_name",
            "goal_description",
            "time_span",
            "end_date",
            "iteration",
            "next_steps",
            "reward",
            "completed",
            "is_paused",
        }
        updates = {k: data[k] for k in data.keys() if k in allowed}
        if "iteration" in updates and updates["iteration"] not in VALID_ITERATIONS:
            return jsonify(
                {"error": f"invalid iteration; must be one of {sorted(VALID_ITERATIONS)}"}
            ), 400

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            params = list(updates.values()) + [goal_id]
            conn.execute(f"UPDATE goals SET {set_clause} WHERE id = ?", params)
            conn.commit()

        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    finally:
        conn.close()

    if "iteration" in updates and updates["iteration"]:
        schedule_reminder(goal_id, updates["iteration"])

    return jsonify(goal_to_dict(row))


@api_bp.route("/goals/<int:goal_id>", methods=["DELETE"])
@require_api_key
def delete_goal(goal_id):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT id FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return jsonify({"error": "Goal not found"}), 404
        conn.execute("DELETE FROM goal_history WHERE goal_id = ?", (goal_id,))
        conn.execute("DELETE FROM iteration_history WHERE iteration_id = ?", (goal_id,))
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
    finally:
        conn.close()
    remove_reminder(goal_id)
    return jsonify({"deleted": goal_id})


@api_bp.route("/goals/<int:goal_id>/complete", methods=["POST"])
@require_api_key
def complete_goal(goal_id):
    data = request.get_json(silent=True) or {}
    was_done = data.get("was_done", "")
    next_steps = data.get("next_steps")
    reward = data.get("reward")
    mark_done = bool(data.get("mark_done", False))

    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return jsonify({"error": "Goal not found"}), 404

        new_next_steps = next_steps if next_steps is not None else row["next_steps"]
        new_reward = reward if reward is not None else row["reward"]

        conn.execute(
            """
            INSERT INTO iteration_history (iteration_id, status, updated_at)
            VALUES (?, ?, ?)
            """,
            (goal_id, "Yes", datetime.now()),
        )
        conn.execute(
            """
            INSERT INTO goal_history (goal_id, completed, was_done, next_steps, reward, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (goal_id, "yes", was_done, new_next_steps, new_reward, datetime.now()),
        )
        conn.execute(
            """
            UPDATE goals SET next_steps = ?, reward = ?, completed = ?, is_paused = 0
            WHERE id = ?
            """,
            (new_next_steps, new_reward, 1 if mark_done else row["completed"], goal_id),
        )
        conn.commit()
    finally:
        conn.close()

    if mark_done:
        remove_reminder(goal_id)

    return jsonify({"ok": True, "goal_id": goal_id, "marked_done": mark_done})


@api_bp.route("/goals/<int:goal_id>/snooze", methods=["POST"])
@require_api_key
def snooze_goal(goal_id):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT id FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return jsonify({"error": "Goal not found"}), 404
        conn.execute("UPDATE goals SET is_paused = 1 WHERE id = ?", (goal_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "goal_id": goal_id, "paused": True})


@api_bp.route("/goals/<int:goal_id>/resume", methods=["POST"])
@require_api_key
def resume_goal(goal_id):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT iteration FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Goal not found"}), 404
        conn.execute("UPDATE goals SET is_paused = 0 WHERE id = ?", (goal_id,))
        conn.commit()
        iteration = row["iteration"]
    finally:
        conn.close()
    if iteration:
        schedule_reminder(goal_id, iteration)
    return jsonify({"ok": True, "goal_id": goal_id, "paused": False})


@api_bp.route("/settings", methods=["GET"])
@require_api_key
def get_settings():
    slot = get_iteration_slot()
    return jsonify(
        {
            "iteration_slot": {
                **slot,
                "weekday_name": WEEKDAY_NAMES[slot["weekday"]],
            },
            "default_email": get_setting("default_email"),
        }
    )


@api_bp.route("/settings", methods=["PATCH"])
@require_api_key
def update_settings():
    data = request.get_json(silent=True) or {}
    changed_slot = False
    slot_update = data.get("iteration_slot") or {}
    if slot_update:
        wd = slot_update.get("weekday")
        hr = slot_update.get("hour")
        mn = slot_update.get("minute")
        if wd is not None and not (0 <= int(wd) <= 6):
            return jsonify({"error": "weekday must be 0..6 (0=Monday)"}), 400
        if hr is not None and not (0 <= int(hr) <= 23):
            return jsonify({"error": "hour must be 0..23"}), 400
        if mn is not None and not (0 <= int(mn) <= 59):
            return jsonify({"error": "minute must be 0..59"}), 400
        set_iteration_slot(weekday=wd, hour=hr, minute=mn)
        changed_slot = True

    if "default_email" in data and data["default_email"]:
        set_setting("default_email", data["default_email"])
        import os as _os
        _os.environ["DEFAULT_TO_ADDRESS"] = data["default_email"]

    rescheduled = []
    if changed_slot:
        rescheduled = reschedule_all_active()

    slot = get_iteration_slot()
    return jsonify(
        {
            "iteration_slot": {**slot, "weekday_name": WEEKDAY_NAMES[slot["weekday"]]},
            "rescheduled_goals": [{"goal_id": gid, "next_run": nxt} for gid, nxt in rescheduled],
        }
    )


@api_bp.route("/goals/<int:goal_id>/history", methods=["GET"])
@require_api_key
def goal_history(goal_id):
    conn = get_db_connection()
    try:
        goal_rows = conn.execute(
            """
            SELECT completed, was_done, next_steps, reward, timestamp
            FROM goal_history WHERE goal_id = ? ORDER BY timestamp DESC
            """,
            (goal_id,),
        ).fetchall()
        iter_rows = conn.execute(
            """
            SELECT status, next_run, updated_at FROM iteration_history
            WHERE iteration_id = ? ORDER BY updated_at DESC
            """,
            (goal_id,),
        ).fetchall()
    finally:
        conn.close()
    return jsonify(
        {
            "goal_history": [dict(r) for r in goal_rows],
            "iteration_history": [dict(r) for r in iter_rows],
        }
    )
