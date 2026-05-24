# Mindbaboon

Goal tracker with iteration-based email reminders. You set a goal, pick a
cadence (week / 2 weeks / month), and the app emails you to check in.
Responding to the email feeds a small history log so you can see the
cycle of attempts over time.

Stack: Flask + SQLite + APScheduler, packaged as Docker. UI gated behind
Google OAuth (email allowlist). Includes a REST API and an MCP server so
you can manage goals from an LLM client (e.g. Claude Code) or any HTTP
tool — the API uses an independent `X-API-Key` so MCP/cron jobs keep
working without browser sessions.

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
is recovered on boot. Missed fires within `misfire_grace_time` (60s) run
on startup; older misses are dropped (`coalesce=True` collapses repeats).
A separate idempotency guard in `send_goal_reminder` refuses to send a
reminder if one was already sent for the same goal within the last hour
— defense against restart races causing duplicate emails.

## Run

Production deployment runs on a Proxmox host (LXC or VM with Docker).
Local Mac/dev box is only used to build and ship — never to "host" the
service. The pieces:

1. Copy `.env.example` to `.env` and fill in SMTP creds and an API key:
   ```bash
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"  # paste into MINDBABOON_API_KEY
   ```
2. On the Proxmox-hosted target, in the project directory:
   ```bash
   docker compose -p mindbaboon up -d --build
   ```
   The `-p mindbaboon` is load-bearing — compose uses it to name the
   data volume (`mindbaboon_mindbaboon_data`). Changing it strands your
   existing DB.
3. Open `http://<proxmox-host>:5000` to confirm the UI loads.

### Critical: never run two instances against the same DB

The scheduler uses a SQLite-backed job store with no inter-process
locking. If you start the app twice against the same database (two
containers, container + bare-metal process, two compose stacks), each
process will independently fire every scheduled job and you'll get
duplicate emails — both startup mail and reminder mail.

Symptoms and diagnostics:

```bash
# 1) Confirm there's exactly one container
docker ps --filter "name=mindbaboon"

# 2) Check the live process count from inside the container
docker exec <container> ps aux | grep python

# 3) Grep the logs — should see exactly one "STARTUP" line per real boot
docker logs <container> 2>&1 | grep STARTUP

# 4) Hit /api/health and note the "pid" + "hostname" fields. Repeated
#    calls should always return the same pid until you restart. If pid
#    flips between two values, that's two processes load-balancing.
curl http://<proxmox-host>:5000/api/health | jq '.pid, .hostname'
```

The app also self-defends: startup emails sent within 5 minutes of an
earlier one are skipped (logged as `WARNING - Skipping startup email`),
and reminder emails for the same goal within an hour are skipped
(`WARNING - Skipping reminder for goal X`). If you see those warnings,
you have two instances and should track down the second one.

## Authentication

UI is gated behind **Google OAuth 2.0** (authorization code flow with
PKCE). On first visit to any UI route, an unauthenticated user is
redirected to `/login`, signs in with Google, and the backend verifies:

1. ID token signature against Google JWKS (via Authlib)
2. `email_verified=true` claim
3. Email is in `ALLOWED_EMAILS` (lowercase exact match)

A 30-day Flask session cookie (`__Host-` prefixed, Secure+HttpOnly+
SameSite=Lax) is set on success. Logout is POST-only with CSRF token.

**API endpoints (`/api/...`) are NOT gated by OAuth** — they keep the
`X-API-Key` header check from `api.py`. This lets MCP servers, cron
jobs, and curl scripts keep working independently of browser sessions.

### Setup (Google OAuth)

1. https://console.cloud.google.com/ → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID, type **Web application**
3. Authorized redirect URI: `https://<SERVER_HOST>/oauth2/callback`
4. Drop `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` into `.env`
5. Set `ALLOWED_EMAILS=you@example.com,...` and `FLASK_SECRET_KEY=...`

### Defense in depth (recommended)

For belt-and-suspenders security, add a **Cloudflare Access** policy
in the Zero Trust dashboard on the same hostname. Cloudflare gates the
edge with your email allowlist before any request hits the docker host.
The app's own OAuth still works for direct LAN/Tailscale access.

Security headers (HSTS, CSP, X-Frame-Options, etc.) are set by
Flask-Talisman. CSRF tokens via Flask-WTF on every POST form.
Rate limiting on `/oauth2/callback` via Flask-Limiter.

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

Valid `iteration` values: `"week"`, `"2 weeks"`, `"month"`. The
`timedelta` kwargs behind these keys live in `config.py`. Note that
`"month"` is implemented as `weeks=4` (28 days), not a calendar month —
over a year this drifts by ~5 days. If you need true calendar-month
cadence, swap the `IntervalTrigger` for a `CronTrigger`.

Quick check after a restart:

```bash
curl http://<proxmox-host>:5000/api/health
# scheduler_running: true, jobs[] with future next_run_time, pid + hostname
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
| `FLASK_SECRET_KEY` | 32-byte hex, signs session cookies. Hard-fail if missing |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Web client |
| `ALLOWED_EMAILS` | Comma-separated lowercase emails permitted to sign in |
| `TZ` | Timezone for scheduler (default `Europe/Prague`) |

Never commit `.env`. It's in `.gitignore`. `docker-compose.yml` loads it
via `env_file:`.

## Data

Single SQLite DB at `/app/data/mindbaboon.db` inside the container,
backed by the `mindbaboon_mindbaboon_data` named volume when running
with `-p mindbaboon`. Tables:

- `goals` — the goals themselves. `is_silenced=1` means the next scheduled
  tick will skip sending email (set when a reminder fires, cleared when the
  user responds via `/iteration/<id>` or `/api/.../resume`).
- `goal_history` — one row per completed iteration, with reflection text
- `iteration_history` — status transitions (Scheduled / yes / no)
- `apscheduler_jobs` — serialized jobs + `next_run_time` (binary blob,
  written by APScheduler)
- `settings` — key/value for things like `default_email` and the global
  iteration slot (`iteration_weekday` / `iteration_hour` / `iteration_minute`)

FK `ON DELETE CASCADE` on `goal_history` and `iteration_history` is wired
up — `get_db_connection()` enables `PRAGMA foreign_keys = ON`, so deleting
a goal automatically removes its history rows.

## License

Personal project, no license file. Ask before reusing.
