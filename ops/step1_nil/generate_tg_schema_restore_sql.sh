#!/usr/bin/env bash
set -euo pipefail

# Generates a plain SQL restore script from a custom-format pg_dump (-Fc) that restores into schema "tg".
#
# Usage:
#   DUMP=kb_ring/server_exports/tg_93_77_185_71/<ts>/tg_digest.dump \
#   OUT=./tg_restore_into_schema_tg.sql \
#   bash kb_ring/ops/step1_nil/generate_tg_schema_restore_sql.sh

DUMP="${DUMP:-}"
OUT="${OUT:-}"

if [[ -z "${DUMP}" || -z "${OUT}" ]]; then
  echo "Usage: DUMP=... OUT=... $0" >&2
  exit 2
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

pg_restore -f "$tmp" "$DUMP"

{
  echo "-- Auto-generated from $DUMP"
  echo "BEGIN;"
  echo "CREATE SCHEMA IF NOT EXISTS tg;"
  echo "SET search_path = tg, public;"
  echo
  cat "$tmp"
  echo
  echo "COMMIT;"
} > "$OUT"

echo "OK: $OUT"

