#!/usr/bin/env bash
set -euo pipefail

# Export TG Digest artifacts from the old server into kb_ring/server_exports/.
#
# Usage:
#   HOST=93.77.185.71 USER=yc-user bash kb_ring/scripts/fetch_tg_exports.sh
#
# Optional:
#   INCLUDE_MEDIA=0|1   (default 0)  # /app/media can be large
#
# Notes:
# - Output directory is gitignored (server_exports/).
# - The export may contain secrets (secrets.env). Do not commit.

HOST="${HOST:-93.77.185.71}"
SSH_USER="${SSH_USER:-yc-user}"
INCLUDE_MEDIA="${INCLUDE_MEDIA:-0}"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/server_exports/tg_${HOST//./_}/${TS}"
umask 077
mkdir -p "${OUT_DIR}"

echo "[1/4] Collecting repo config files"
ssh "${SSH_USER}@${HOST}" "tar -czf - --ignore-failed-read \
  /home/yc-user/tg_digest_system/tg_digest_system/docker/docker-compose.yml \
  /home/yc-user/tg_digest_system/tg_digest_system/docker/.env \
  /home/yc-user/tg_digest_system/tg_digest_system/docker/secrets.env \
  /home/yc-user/tg_digest_system/tg_digest_system/config/channels.json \
  /home/yc-user/tg_digest_system/tg_digest_system/prompts \
  2>/dev/null || true" > "${OUT_DIR}/tg_config.tgz"
tar -xzf "${OUT_DIR}/tg_config.tgz" -C "${OUT_DIR}"

echo "[2/4] Exporting telethon.session from container"
ssh "${SSH_USER}@${HOST}" "docker cp tg_digest_worker:/app/data/telethon.session - 2>/dev/null" > "${OUT_DIR}/telethon.session" || true

echo "[3/4] Exporting database dump (pg_dump -Fc) from container"
# We try without password prompt first; if it fails, we still keep the rest of the export.
ssh "${SSH_USER}@${HOST}" "docker exec tg_digest_postgres pg_dump -Fc -U tg_digest -d tg_digest 2>/dev/null" > "${OUT_DIR}/tg_digest.dump" || true

echo "[4/4] Media/logs (optional)"
if [[ "${INCLUDE_MEDIA}" == "1" ]]; then
  echo "  INCLUDE_MEDIA=1 -> exporting /app/media (can be large)"
  ssh "${SSH_USER}@${HOST}" "tar -czf - --ignore-failed-read \
    -C /var/lib/docker/volumes/tg_digest_worker_media/_data . \
    2>/dev/null || true" > "${OUT_DIR}/worker_media.tgz" || true
else
  echo "  INCLUDE_MEDIA=0 -> skipping media export; writing size manifest"
  ssh "${SSH_USER}@${HOST}" "docker exec tg_digest_worker sh -lc 'du -sh /app/media /app/logs /app/data 2>/dev/null; find /app/media -maxdepth 2 -type d 2>/dev/null | head -200' 2>/dev/null || true" > "${OUT_DIR}/MEDIA_MANIFEST.txt"
fi

cat > "${OUT_DIR}/NOTES.txt" <<EOF
Host: ${HOST}
User: ${SSH_USER}
Timestamp: ${TS}

Files:
- tg_config.tgz: docker/config/prompts (may include secrets.env)
- telethon.session: extracted from tg_digest_worker:/app/data/telethon.session
- tg_digest.dump: pg_dump -Fc from tg_digest_postgres (may be empty if pg_dump failed)
- MEDIA_MANIFEST.txt: sizes/dirs (if INCLUDE_MEDIA=0)
- worker_media.tgz: media tarball (if INCLUDE_MEDIA=1)
EOF

echo "OK: ${OUT_DIR}"
