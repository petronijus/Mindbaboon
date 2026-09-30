# Changelog

All notable changes to Mindbaboon. Format follows
[Keep a Changelog](https://keepachangelog.com/), versioning follows
[SemVer](https://semver.org/) (0.x = no stability promises).

The single source of truth for the version is `VERSION` in `config.py`.

## [Unreleased]

## [0.12.0] - 2026-09-30

### Added
- `EMAIL_FROM` sets the reminder sender separately from the SMTP login, so
  mail can go through a transactional relay such as Resend (it logs in as
  `resend` and needs a `From` on a verified domain). Unset, it falls back to
  `EMAIL_USERNAME`, so a plain SMTP setup keeps working unchanged.

### Changed
- Python dependencies are now installed from hash-pinned lockfiles
  (`requirements.lock`, `mcp_server/requirements.lock`, regenerated with
  `scripts/deps-lock.sh`); the Dockerfile uses `pip install --require-hashes`.
  The loose `requirements.txt` files remain the human-edited intent.
- MCP server migrated to `mcp` SDK 2.x (`MCPServer`); the 1.x `FastMCP`
  module no longer exists in 2.0+, so a fresh install had been failing to
  import. Bounded to `mcp>=2.0.0,<3`.
- MCP server dependencies refreshed to the latest patches (`sse-starlette`
  3.4.11).

## [0.11.2]

First public release.

### Features
- Goal tracker with iteration-based email reminders (week / 2 weeks / month
  cadence); responding to a reminder feeds a per-goal history log.
- Flask + SQLite + APScheduler, packaged as Docker; timers survive container
  restarts via a SQLAlchemy job store in the same SQLite DB.
- UI gated behind Google OAuth 2.0 (PKCE) with an email allowlist.
- REST API (`/api/...`) with independent `X-API-Key` auth, plus a standalone
  MCP server (`mcp_server/`) so goals can be managed from an LLM client.
- Self-defenses against duplicate emails: startup-email and per-goal reminder
  idempotency guards; `/api/health` exposes pid/hostname for split-brain checks.
