#!/usr/bin/env bash
# Build the Mindbaboon image LOCALLY and push it to GHCR. Deploy then pulls it
# (docker compose pull) — the build does not run on the VM or in GitHub CI.
#
# Prereqs (on your build machine):
#   - Docker running
#   - logged in to GHCR:  echo "$GHCR_PAT" | docker login ghcr.io -u petronijus --password-stdin
#       (PAT needs write:packages)
#
# Usage:
#   scripts/build-push.sh              # tag = VERSION file + :latest
#   MINDBABOON_TAG=0.11.3 scripts/build-push.sh
set -euo pipefail
cd "$(dirname "$0")/.."

REG="ghcr.io/petronijus/mindbaboon"
TAG="${MINDBABOON_TAG:-$(cat VERSION)}"

echo "→ building ${REG}:${TAG} (+ latest)"
docker build -t "${REG}:${TAG}" -t "${REG}:latest" .
docker push "${REG}:${TAG}"
docker push "${REG}:latest"
echo "✓ pushed ${REG}:{${TAG},latest}"
echo "  Deploy:  docker compose -p mindbaboon pull && docker compose -p mindbaboon up -d"
