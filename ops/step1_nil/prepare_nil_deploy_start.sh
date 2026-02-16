#!/usr/bin/env bash
set -euo pipefail

# Prepare Nil server for deploy start:
# - create config backup bundle
# - ensure target directories for KB-RING exist
# - add logbook entry on server (/opt/server-docs/logbook.md)
#
# Usage:
#   NIL_SSH=vps-ripas-229 bash ops/step1_nil/prepare_nil_deploy_start.sh

NIL_SSH="${NIL_SSH:-vps-ripas-229}"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/opt/backups/kb_ring_deploy_start_${TS}"
REMOTE_NOTE="/tmp/kb_ring_logbook_${TS}.md"

cat > "/tmp/kb_ring_logbook_${TS}.md.local" <<EOF
## 2026-02-16 - Подготовка к деплою KB-RING (этап start)

### Backup + predeploy подготовка
- Дата: 2026-02-16, ${TS}
- Операция: Подготовка сервера к старту деплоя KB-RING по правилам maintenance-rules.md
- Детали:
  - Создан predeploy backup: ${BACKUP_DIR}
  - Сохранены конфиги Caddy/monitoring/server-docs
  - Проверены/подготовлены каталоги: /opt/kb-ring, /opt/tg_digest_system
  - Зафиксирован факт удаления старого transcription-контура
- Результат: Сервер подготовлен к началу развёртывания KB-RING, базовые конфиги и документация сохранены
EOF

ssh "${NIL_SSH}" "
  set -euo pipefail
  sudo -n install -d -m 755 '${BACKUP_DIR}'
  sudo -n install -d -m 755 /opt/kb-ring /opt/tg_digest_system
  sudo -n chown -R alexey:alexey /opt/kb-ring /opt/tg_digest_system

  sudo -n cp -a /etc/caddy/Caddyfile '${BACKUP_DIR}/Caddyfile.bak' || true
  sudo -n cp -a /opt/monitoring/docker-compose.yml '${BACKUP_DIR}/monitoring-docker-compose.yml.bak' || true
  sudo -n cp -a /opt/monitoring/prometheus/prometheus.yml '${BACKUP_DIR}/prometheus.yml.bak' || true
  sudo -n cp -a /opt/monitoring/prometheus/alerts.yml '${BACKUP_DIR}/alerts.yml.bak' || true
  sudo -n cp -a /opt/server-docs '${BACKUP_DIR}/server-docs.bak' || true

  echo 'backup_dir=${BACKUP_DIR}'
  ls -la '${BACKUP_DIR}' | sed -n '1,80p'
"

scp "/tmp/kb_ring_logbook_${TS}.md.local" "${NIL_SSH}:${REMOTE_NOTE}" >/dev/null
ssh "${NIL_SSH}" "
  set -euo pipefail
  sudo -n sh -c 'cat ${REMOTE_NOTE} >> /opt/server-docs/logbook.md'
  rm -f '${REMOTE_NOTE}'
  tail -n 20 /opt/server-docs/logbook.md
"

rm -f "/tmp/kb_ring_logbook_${TS}.md.local"
echo "Prepared Nil deploy start. Backup: ${BACKUP_DIR}"
