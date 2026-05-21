"""Mindbaboon MCP server.

Exposes Mindbaboon goal management to LLM clients (Claude Code, etc.) over
stdio. Wraps the REST API at MINDBABOON_URL using X-API-Key auth.

Env vars:
  MINDBABOON_URL       default http://localhost:5000
  MINDBABOON_API_KEY   required, must match the server's key
"""
from __future__ import annotations

import os
import json
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("MINDBABOON_URL", "http://localhost:5000").rstrip("/")
API_KEY = os.getenv("MINDBABOON_API_KEY", "")

mcp = FastMCP("mindbaboon")


def _client() -> httpx.Client:
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    return httpx.Client(base_url=BASE_URL, headers=headers, timeout=10.0)


def _unwrap(resp: httpx.Response) -> Any:
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"error": True, "status": resp.status_code, "body": body}
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


@mcp.tool()
def health() -> dict:
    """Check Mindbaboon server health, scheduler state, and scheduled jobs.

    Use this first if a user suspects a timer/reminder stopped working or
    Docker crashed. Shows whether the scheduler is running and the next
    run time for every active job.
    """
    with _client() as c:
        return _unwrap(c.get("/api/health"))


@mcp.tool()
def list_goals(include_completed: bool = False) -> Any:
    """List goals. By default only active (not completed) goals."""
    with _client() as c:
        return _unwrap(
            c.get("/api/goals", params={"include_completed": str(include_completed).lower()})
        )


@mcp.tool()
def get_goal(goal_id: int) -> Any:
    """Fetch a single goal by id, including its next scheduled reminder time."""
    with _client() as c:
        return _unwrap(c.get(f"/api/goals/{goal_id}"))


@mcp.tool()
def create_goal(
    goal_name: str,
    goal_description: str,
    time_span: str,
    iteration: str,
    next_steps: str,
    reward: str,
    end_date: str = "",
) -> Any:
    """Create a new goal and schedule its reminder.

    ALL fields are required — the server rejects partial goals.

    - goal_name: one-line title
    - goal_description: short description (one sentence)
    - time_span: "weeks" | "months" | "specific_date"
    - iteration: "week" | "2 weeks" | "month"  (reminder cadence)
    - next_steps: what you commit to do before the next check-in
    - reward: what you'll give yourself
    - end_date: REQUIRED (YYYY-MM-DD) when time_span="specific_date"
    """
    payload = {
        "goal_name": goal_name,
        "goal_description": goal_description,
        "time_span": time_span,
        "iteration": iteration,
        "next_steps": next_steps,
        "reward": reward,
        "end_date": end_date or None,
    }
    with _client() as c:
        return _unwrap(c.post("/api/goals", json=payload))


@mcp.tool()
def update_goal(
    goal_id: int,
    goal_name: str,
    goal_description: str,
    time_span: str,
    iteration: str,
    next_steps: str,
    reward: str,
    end_date: str = "",
) -> Any:
    """Full update of a goal — same required fields as create_goal.
    For pausing or completing a goal, use snooze_goal/resume_goal/complete_iteration
    instead. If you only know the goal_id, call get_goal first to read the current
    values before changing individual fields.
    """
    payload = {
        "goal_name": goal_name,
        "goal_description": goal_description,
        "time_span": time_span,
        "iteration": iteration,
        "next_steps": next_steps,
        "reward": reward,
        "end_date": end_date or None,
    }
    with _client() as c:
        return _unwrap(c.patch(f"/api/goals/{goal_id}", json=payload))


@mcp.tool()
def delete_goal(goal_id: int) -> Any:
    """Delete a goal and its history, and remove its scheduled reminder."""
    with _client() as c:
        return _unwrap(c.delete(f"/api/goals/{goal_id}"))


@mcp.tool()
def complete_iteration(
    goal_id: int,
    was_done: str = "",
    next_steps: str | None = None,
    reward: str | None = None,
    mark_done: bool = False,
) -> Any:
    """Record that the current iteration of a goal was completed.
    Set mark_done=True to close the goal entirely and stop reminders."""
    payload: dict[str, Any] = {"was_done": was_done, "mark_done": mark_done}
    if next_steps is not None:
        payload["next_steps"] = next_steps
    if reward is not None:
        payload["reward"] = reward
    with _client() as c:
        return _unwrap(c.post(f"/api/goals/{goal_id}/complete", json=payload))


@mcp.tool()
def snooze_goal(goal_id: int) -> Any:
    """Silence reminder emails for a goal (sets is_silenced=1). The APScheduler
    job keeps ticking on its cadence but the handler skips sending until the
    flag is cleared via resume_goal or by responding to the iteration form."""
    with _client() as c:
        return _unwrap(c.post(f"/api/goals/{goal_id}/snooze"))


@mcp.tool()
def resume_goal(goal_id: int) -> Any:
    """Clear the silenced flag so the next scheduled tick can send email again."""
    with _client() as c:
        return _unwrap(c.post(f"/api/goals/{goal_id}/resume"))


@mcp.tool()
def get_settings() -> Any:
    """Get current settings, including the global iteration slot (weekday + time
    when all reminders fire) and the default email address."""
    with _client() as c:
        return _unwrap(c.get("/api/settings"))


@mcp.tool()
def update_settings(
    weekday: int | None = None,
    hour: int | None = None,
    minute: int | None = None,
    default_email: str | None = None,
) -> Any:
    """Update the global iteration slot and/or default email. Changing the slot
    reschedules all active goals to align with the new window.

    weekday: 0=Monday .. 6=Sunday. hour: 0..23. minute: 0..59.
    Pass only fields you want to change.
    """
    body: dict[str, Any] = {}
    slot: dict[str, Any] = {}
    if weekday is not None:
        slot["weekday"] = weekday
    if hour is not None:
        slot["hour"] = hour
    if minute is not None:
        slot["minute"] = minute
    if slot:
        body["iteration_slot"] = slot
    if default_email is not None:
        body["default_email"] = default_email
    with _client() as c:
        return _unwrap(c.patch("/api/settings", json=body))


@mcp.tool()
def goal_history(goal_id: int) -> Any:
    """Get both goal_history and iteration_history for a goal."""
    with _client() as c:
        return _unwrap(c.get(f"/api/goals/{goal_id}/history"))


if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("MINDBABOON_API_KEY is required")
    mcp.run()
