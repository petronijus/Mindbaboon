# Mindbaboon MCP server

Lets Claude Code (or any MCP client) create, complete, snooze, and query
goals in your running Mindbaboon instance.

## Setup

```bash
pip install -r mcp_server/requirements.txt
```

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

- `health` — scheduler state, job count, next_run_time list
- `list_goals(include_completed=False)`
- `get_goal(goal_id)`
- `create_goal(goal_name, iteration, ...)` — iteration ∈ {"week","2 weeks","month"}
- `update_goal(goal_id, updates)`
- `delete_goal(goal_id)`
- `complete_iteration(goal_id, was_done, next_steps?, reward?, mark_done=False)`
- `snooze_goal(goal_id)` / `resume_goal(goal_id)`
- `goal_history(goal_id)`
