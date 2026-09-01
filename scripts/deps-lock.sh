#!/usr/bin/env bash
# Regenerate the hash-pinned lockfiles from the loose requirements files.
#
# requirements.txt / mcp_server/requirements.txt hold the *intent* (floors and
# upper bounds); requirements.lock / mcp_server/requirements.lock hold the exact
# resolve the Docker image and the MCP server install from. Run this after
# editing either requirements file, then commit both files together.
#
# Resolves for Python 3.11 (the Dockerfile base) regardless of the host
# interpreter, and emits --hash lines so `pip install --require-hashes` fails
# closed on a tampered or substituted package.
#
# Prereq: uv (https://docs.astral.sh/uv/) on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/)" >&2; exit 1; }

lock() {
  local src="$1" out="$2"
  echo "→ ${src} → ${out}"
  uv pip compile --quiet --python-version 3.11 --generate-hashes --no-header "$src" -o "$out"
}

lock requirements.txt requirements.lock
lock mcp_server/requirements.txt mcp_server/requirements.lock
echo "✓ lockfiles regenerated — review the diff and commit them with the requirements change"
