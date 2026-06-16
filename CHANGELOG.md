# Changelog

All notable changes to Mindbaboon. Format follows
[Keep a Changelog](https://keepachangelog.com/), versioning follows
[SemVer](https://semver.org/) (0.x = no stability promises).

The single source of truth for the version is `VERSION` in `config.py`.

## [Unreleased]

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
