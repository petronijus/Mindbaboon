# Mindbaboon MCP server

Lets Claude Code (or any MCP client) create, complete, snooze, and query
goals in your running Mindbaboon instance.

## Setup

Requires the `mcp` SDK 2.x (`mcp.server.mcpserver.MCPServer`); install from the
hash-pinned lockfile so you get exactly the tested resolve:

```bash
pip install --require-hashes -r mcp_server/requirements.lock
```

(`mcp_server/requirements.txt` is the loose intent; regenerate the lock with
`scripts/deps-lock.sh` after editing it.)

Set a strong API key in the main app's `.env`:

```
MINDBABOON_API_KEY=<long random string, e.g. `openssl rand -hex 32`>
```

Restart the Flask app (`docker compose up -d --build`).

## Register with Claude Code

Add to `~/.claude.json` (or project `.mcp.json`):

```json
{
  "mcpServers": {
    "mindbaboon": {
      "command": "python",
      "args": ["D:/Mindbaboon/mcp_server/server.py"],
      "env": {
        "MINDBABOON_URL": "http://localhost:5000",
        "MINDBABOON_API_KEY": "<same key as in .env>"
      }
    }
  }
}
```

Then in Claude Code: `/mcp` to verify, or just say "add a goal to read 20
minutes every week" and it will call `create_goal`.

## Tools exposed

Every tool wraps one REST endpoint and returns the server's JSON as-is. Non-2xx
responses come back as data (`{"error": true, "status": ..., "body": ...}`), not
as a tool error, so the LLM can read the validation message.

- `health()` — scheduler state, job count, `next_run_time` per job (unauthenticated on the server side)
- `list_goals(include_completed=False)`
- `get_goal(goal_id)`
- `create_goal(goal_name, goal_description, time_span, iteration, next_steps, reward, end_date="")` —
  all six fields are required by the server; `time_span` ∈ {`weeks`, `months`, `specific_date`},
  `iteration` ∈ {`week`, `2 weeks`, `month`}, `end_date` (YYYY-MM-DD) required when `time_span="specific_date"`
- `update_goal(goal_id, goal_name, goal_description, time_span, iteration, next_steps, reward, end_date="")` —
  full replace with the same six fields; read the current values with `get_goal` first
- `delete_goal(goal_id)` — removes the goal, its history and its scheduled reminder
- `complete_iteration(goal_id, was_done="", next_steps=None, reward=None, mark_done=False)` —
  `mark_done=True` closes the goal and stops reminders
- `snooze_goal(goal_id)` / `resume_goal(goal_id)` — set / clear `is_silenced`
- `get_settings()` / `update_settings(weekday=None, hour=None, minute=None, default_email=None)` —
  the global iteration slot (`weekday` 0=Monday..6) and default email; pass only what changes
- `goal_history(goal_id)` — both `goal_history` and `iteration_history`
