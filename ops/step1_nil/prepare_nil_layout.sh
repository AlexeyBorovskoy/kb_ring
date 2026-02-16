#!/usr/bin/env bash
set -euo pipefail

# Prepare directories on Nil server for Step 1 migration.
#
# Usage:
#   NIL_SSH=vps-ripas-229 bash kb_ring/ops/step1_nil/prepare_nil_layout.sh

NIL_SSH="${NIL_SSH:-vps-ripas-229}"

ssh "${NIL_SSH}" '
  set -e
  sudo install -d -m 755 /opt/kb-ring
  sudo install -d -m 755 /opt/kb-ring/data
  sudo install -d -m 755 /opt/kb-ring/data/imports
  sudo install -d -m 755 /opt/kb-ring/data/tg_config
  sudo install -d -m 755 /opt/kb-ring/data/telethon
  sudo install -d -m 755 /opt/tg_digest_system
  sudo chown -R alexey:alexey /opt/kb-ring /opt/tg_digest_system
  echo "Prepared directories:"
  ls -ld /opt/kb-ring /opt/tg_digest_system /opt/kb-ring/data/imports
'

echo "OK: Nil layout prepared on ${NIL_SSH}"

