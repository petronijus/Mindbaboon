# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Goal tracker with iteration-based email reminders. Flask + SQLite + APScheduler, packaged with Docker. Exposes a REST API and a sibling MCP server so an LLM client can manage goals.

## Run

Local (no container):
```bash
pip install -r requirements.txt
cp .env.example .env   # then fill SMTP creds + MINDBABOON_API_KEY
python init_mindbaboon_db.py
python mindbaboon.py            # serves on 0.0.0.0:5000
```

Docker (the canonical way):
```bash
docker compose -p mindbaboon up -d --build
```

**The `-p mindbaboon` is load-bearing** — Compose derives the data volume name (`mindbaboon_mindbaboon_data`) from it. Bringing the stack up without that flag creates a *different* volume and strands the existing DB.

Health check after restart:
```bash
curl http://localhost:5000/api/health   # no auth required for this one
```
Look for `scheduler_running: true` and each `jobs[].next_run_time` in the future.

There is no test suite, no lint config, no build step beyond the Docker image.

## Architecture

Single Flask app, three blueprints, one APScheduler instance shared across them. Everything persists in one SQLite file (`data/mindbaboon.db` locally, `/app/data/mindbaboon.db` in container) — including the APScheduler job store.

| File | Role |
|---|---|
| `mindbaboon.py` | Flask app entry; UI routes (`/`, `/add`, `/edit/<id>`, `/delete_goal`, `/settings`), starts scheduler, sends startup email |
| `iteration.py` | Blueprint `/iteration/<id>` — the form linked from reminder emails (Yes/No + reflection) |
| `api.py` | Blueprint `/api/...` — REST, gated by `X-API-Key` header against `MINDBABOON_API_KEY` env var |
| `scheduler.py` | Singleton `BackgroundScheduler` backed by `SQLAlchemyJobStore` on the same SQLite file; email rendering + SMTP send |
| `database.py` | Thin SQLite helpers + `settings` key/value table accessors (`get_iteration_slot`, etc.) |
| `init_mindbaboon_db.py` | Idempotent schema bootstrap; run on container build and on every container start (compose `command`) |
| `config.py` | `VERSION`, `ITERATION_INTERVALS`, `DEFAULT_ITERATION_SLOT`, motivational quotes |
| `mcp_server/server.py` | FastMCP stdio server wrapping the REST API for Claude Code |

### Scheduling model — the one non-obvious bit

There is one APScheduler `interval` job per active goal, id `goal_{goal_id}`. Two pieces of state interact:

1. **Per-goal cadence** — `ITERATION_INTERVALS` in `config.py` (`week` / `2 weeks` / `month`) maps to `timedelta(**args)`; the keys are passed directly to `timedelta`. **Currently set to real cadences (weeks=1/2/4); historic comments still reference short-for-testing values — verify before changing.**
2. **Global iteration slot** — `weekday + hour + minute` stored in the `settings` table (`get_iteration_slot()`). `next_iteration_slot()` rounds the first fire to the next occurrence of that window; subsequent fires drift by the cadence interval. Changing the slot via `/settings` calls `reschedule_all_active()`, which tears down and re-creates every job.

When a reminder fires (`send_goal_reminder`), the goal is **automatically set `is_silenced = 1`**. This is the key bit of the design: the APScheduler job keeps ticking on real-world cadence (so the clock doesn't reset when you respond), but the handler skips sending email until the flag is cleared. Cleared by: user responding via `/iteration/<id>` (form POST), or by `/api/.../resume`. A reminder email fired into a silenced goal is just a no-op — no email, scheduler advances to the next slot.

`is_silenced` was named `is_paused` historically; existing DBs are migrated automatically by `init_mindbaboon_db.py` on startup.

Job persistence: `apscheduler_jobs` table lives in the same SQLite DB. `next_run_time` survives container restarts. Misfires within `misfire_grace_time` (60s) catch up on boot; older are dropped (`coalesce=True`).

`send_goal_reminder` has an idempotency guard using `last_email_sent`: if a reminder went out within the last hour for the same goal, the next fire skips. This is defense against container-restart races where the same scheduled fire could fire twice within the grace window.

Timezone is `Europe/Prague` everywhere (`pytz.timezone('Europe/Prague')` in both `scheduler.py` and `iteration.py`, also pinned in `Dockerfile` and `docker-compose.yml`).

### Email rendering

`render_email(email_type, context)` looks up `templates/emails/<email_type>.html`, renders with Jinja, and pulls the subject from `<title>` in the rendered HTML unless `context["subject"]` is set. Three email types: `startup_email`, `confirmation_email` (on goal creation), `normal_email` (the iteration reminder).

### API auth

`require_api_key` decorator checks `X-API-Key` against `MINDBABOON_API_KEY` with `secrets.compare_digest`. If the env var is unset the endpoint returns 503 — so a misconfigured `.env` fails closed, not open. `/api/health` is the only unauthenticated endpoint.

### UI auth (Google OAuth)

`auth.py` defines `auth_bp` and `require_login` decorator. Flow uses Authlib's Google OAuth client with PKCE — `/login` → `/login/google` (Authlib redirect) → `/oauth2/callback`. The callback verifies the ID token claims, enforces `email_verified=true`, and checks the email against `ALLOWED_EMAILS` (lowercase set) before populating `session['user']`. Session cookies use the `__Host-` prefix, Secure, HttpOnly, SameSite=Lax, 30-day lifetime.

Security middleware wired in `mindbaboon.py`:
- `ProxyFix(x_for=1, x_proto=1, x_host=1)` — required so `url_for(_external=True)` produces HTTPS URLs that match the GCP redirect URI (Cloudflare terminates TLS, forwards HTTP)
- `CSRFProtect(app)` + `csrf.exempt(api_bp)` — UI POSTs need `{{ csrf_token() }}` hidden input, API stays exempt
- `Talisman` — HSTS, CSP (allows typekit.net for fonts + form-action to accounts.google.com for OAuth redirect), X-Frame-Options=DENY, Referrer-Policy
- `Flask-Limiter` — memory-backed, ready for `@limiter.limit(...)` decorators

Adding a new UI route: `@require_login` on the view, `{{ csrf_token() }}` in any POST form template. Adding a new API route: register on `api_bp` and use `@require_api_key` — CSRF + login decorators don't apply.

Goal create/update both require the **full six-field payload** (`goal_name`, `goal_description`, `time_span`, `iteration`, `next_steps`, `reward`, plus `end_date` when `time_span=="specific_date"`). For state changes use the dedicated endpoints — `/complete`, `/snooze`, `/resume` — they don't take the full form.

## Conventions worth knowing

- The Flask app is invoked as `python mindbaboon.py` (the gunicorn line in the Dockerfile is commented out). The compose `command` does `init_mindbaboon_db.py && python mindbaboon.py`. The Python entry point also calls `initialize_database()` itself, so direct `python mindbaboon.py` is safe too.
- All DB writes go through `database.get_db_connection()`; no ORM. `PRAGMA foreign_keys = ON` is enabled on every connection. Schema lives in **one place**: `init_mindbaboon_db.py` (idempotent, includes column-rename migrations).
- `SERVER_HOST` is what email reminder links point to — if unset or `0.0.0.0`, falls back to `socket.gethostbyname(socket.gethostname())`, which **inside a container resolves to `127.0.0.1`**, producing reminder links nobody can click. Always set it explicitly to the public FQDN (e.g. `mindbaboon.bastla.com`); `scheduler._base_url()` then emits `https://<fqdn>` (no port, Cloudflare-terminated) for a public dotted host, and `http://<host>:5000` for LAN/loopback hosts. **The source of truth is NOT `.env`** — it's the SOPS-encrypted `private/config/env.sops` (see Secrets in README). Editing `.env` directly is a trap: the next `./scripts/secrets-decrypt.sh` regenerates `.env` from the SOPS file and clobbers the change. Fix `SERVER_HOST` via `./scripts/secrets-edit.sh`, then decrypt + restart the container.
- The version lives in the `VERSION` file (read by `config.py`); it's rendered in the footer of every template and shown in `/api/health`. Don't hand-edit it for releases — the `repo-release` flow bumps it from a `vX.Y.Z` tag.
- Commits follow Conventional Commits (`feat:` / `fix:` / `chore:` / `docs:`) so `repo-release` can infer the bump level and group the changelog.
