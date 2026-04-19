# Mindbaboon

Goal tracker with iteration-based email reminders. You set a goal, pick a
cadence (week / 2 weeks / month), and the app emails you to check in.
Responding to the email feeds a small history log so you can see the
cycle of attempts over time.

Stack: Flask + SQLite + APScheduler, packaged as Docker. Includes a REST
API and an MCP server so you can manage goals from an LLM client
(e.g. Claude Code) or any HTTP tool.

## Architecture

| Piece | What it is |
|---|---|
| `mindbaboon.py` | Flask app (UI routes: `/`, `/add`, `/edit`, `/settings`) |
| `iteration.py` | Blueprint handling the iteration response flow (`/iteration/<id>`) |
| `api.py` | REST API blueprint (`/api/...`), API-key auth |
| `scheduler.py` | APScheduler + email sender, persistent via SQLAlchemyJobStore |
| `database.py` | SQLite helpers |
| `init_mindbaboon_db.py` | Idempotent schema init |
| `mcp_server/` | Standalone MCP server wrapping the REST API |

Timers survive container restarts: APScheduler stores jobs in the
`apscheduler_jobs` table in the same SQLite DB as goals, so `next_run_time`
is recovered on boot. Missed fires within `misfire_grace_time` (1h) run
on startup.

## Run

1. Copy `.env.example` to `.env` and fill in SMTP creds and an API key:
   ```bash
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"  # paste into MINDBABOON_API_KEY
   ```
2. ```bash
   docker compose -p mindbaboon up -d --build
   ```
   The `-p mindbaboon` is important — compose uses it to name the data
   volume. Changing it strands your existing DB.
3. Open http://localhost:5000 (or your server's hostname).

## REST API

Base URL `/api`. Every endpoint except `/api/health` requires the
`X-API-Key` header.

| Method | Path | |
|---|---|---|
| GET | `/api/health` | Scheduler state, job count, each job's next_run_time |
| GET | `/api/goals?include_completed=false` | List goals |
| POST | `/api/goals` | Create goal (+ schedule if `iteration` set) |
| GET | `/api/goals/<id>` | Single goal |
| PATCH | `/api/goals/<id>` | Update allowed fields |
| DELETE | `/api/goals/<id>` | Delete goal and its history |
| POST | `/api/goals/<id>/complete` | Record iteration completion |
| POST | `/api/goals/<id>/snooze` | Pause reminders |
| POST | `/api/goals/<id>/resume` | Resume and reschedule |
| GET | `/api/goals/<id>/history` | Goal + iteration history |

Valid `iteration` values: `"week"`, `"2 weeks"`, `"month"`. The minute
counts behind these keys live in `config.py` (currently short-for-testing
values — production cadences should be adjusted there).

Quick check after a restart:

```bash
curl http://<host>:5000/api/health
# scheduler_running: true, jobs[] with future next_run_time
```

## MCP server

`mcp_server/` exposes the REST API as MCP tools so an LLM can create
goals, mark iterations done, snooze, and query state. Setup is in
[mcp_server/README.md](mcp_server/README.md).

## Env vars

| Var | Purpose |
|---|---|
| `EMAIL_SMTP_SERVER`, `EMAIL_SMTP_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD` | SMTP for outbound mail |
| `DEFAULT_TO_ADDRESS` | Who receives reminders |
| `SERVER_HOST` | Hostname used in email reminder links |
| `MINDBABOON_API_KEY` | Required to call `/api/...` (except `/health`) |
| `TZ` | Timezone for scheduler (default `Europe/Prague`) |

Never commit `.env`. It's in `.gitignore`. `docker-compose.yml` loads it
via `env_file:`.

## Data

Single SQLite DB at `/app/data/mindbaboon.db` inside the container,
backed by the `mindbaboon_mindbaboon_data` named volume when running
with `-p mindbaboon`. Tables:

- `goals` — the goals themselves
- `goal_history` — one row per completed iteration, with reflection text
- `iteration_history` — status transitions (Scheduled / Yes / No)
- `apscheduler_jobs` — serialized jobs + `next_run_time` (binary blob,
  written by APScheduler)
- `settings` — key/value for things like `default_email`

## License

Personal project, no license file. Ask before reusing.
