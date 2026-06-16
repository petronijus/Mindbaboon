#!/usr/bin/env bash
# Edit the SOPS-encrypted secrets in $EDITOR (decrypt -> edit -> re-encrypt in place).
# Commit the updated private/config/env.sops in the private overlay afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
ENC="private/config/env.sops"
KEY_ITEM="SOPS age key (dev repos)"
command -v sops >/dev/null || { echo "sops not found — 'brew install sops age'"; exit 1; }
command -v op   >/dev/null || { echo "op (1Password CLI) not found"; exit 1; }
[ -f "$ENC" ] || { echo "Missing $ENC — clone the private overlay into ./private first."; exit 1; }
key="$(op document get "$KEY_ITEM" 2>/dev/null)" || { echo "Could not read '$KEY_ITEM' from 1Password."; exit 1; }
SOPS_AGE_KEY="$(printf '%s' "$key" | grep '^AGE-SECRET-KEY')" \
  sops --input-type binary --output-type binary "$ENC"
echo "Re-encrypted $ENC — commit it in the private overlay."
