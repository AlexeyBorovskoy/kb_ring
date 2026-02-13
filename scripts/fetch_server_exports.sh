#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   HOST=89.124.65.229 USER=alexey bash kb_ring/scripts/fetch_server_exports.sh
#
# Exports are stored in kb_ring/server_exports/<timestamp>/.

HOST="${HOST:-89.124.65.229}"
USER="${USER:-alexey}"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/server_exports/${TS}"
mkdir -p "${OUT_DIR}"

echo "[1/3] Exporting files from ${USER}@${HOST} -> ${OUT_DIR}"

# Try to read /etc/caddy/Caddyfile; may require root. We still attempt.
ssh "${USER}@${HOST}" "tar -czf - --ignore-failed-read \
  /opt/transcription/.env \
  /etc/systemd/system/transcription.service \
  /etc/caddy/Caddyfile \
  /opt/monitoring \
  /opt/server-docs \
  /opt/transcription/uploads \
  /opt/transcription/results \
  /opt/transcription/data \
  2>/tmp/kb_ring_export_tar.err || true" > "${OUT_DIR}/server_export.tgz"

echo "[2/3] Extracting archive"
tar -xzf "${OUT_DIR}/server_export.tgz" -C "${OUT_DIR}"

echo "[3/3] Writing notes"
cat > "${OUT_DIR}/NOTES.txt" <<EOF
Host: ${HOST}
User: ${USER}
Timestamp: ${TS}

If some files were missing/unreadable (e.g. /etc/caddy/Caddyfile), check:
- ${OUT_DIR}/server_export.tgz
and re-run with appropriate privileges.
EOF

echo "OK: ${OUT_DIR}"

