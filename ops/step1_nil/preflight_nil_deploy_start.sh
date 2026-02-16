#!/usr/bin/env bash
set -euo pipefail

# Nil deploy-start preflight.
# Checks server readiness before first deployment actions.
#
# Usage:
#   NIL_SSH=vps-ripas-229 bash ops/step1_nil/preflight_nil_deploy_start.sh

NIL_SSH="${NIL_SSH:-vps-ripas-229}"
TS="$(date +%Y%m%d_%H%M%S)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="${ROOT_DIR}/reports"
REPORT_FILE="${REPORT_DIR}/preflight_${TS}.md"

mkdir -p "${REPORT_DIR}"

cat > "${REPORT_FILE}" <<EOF
# Nil Preflight Report

- Generated at: ${TS}
- Target: ${NIL_SSH}

## Summary
EOF

ok=0
warn=0
fail=0

append_line() {
  local status="$1"
  local text="$2"
  echo "- [${status}] ${text}" >> "${REPORT_FILE}"
}

run_remote() {
  local cmd="$1"
  ssh -o BatchMode=yes -o ConnectTimeout=12 "${NIL_SSH}" "${cmd}"
}

if run_remote "echo 'pong' >/dev/null"; then
  append_line "OK" "SSH доступ к серверу подтвержден"
  ((ok+=1))
else
  append_line "FAIL" "SSH недоступен"
  ((fail+=1))
fi

if run_remote "sudo -n true >/dev/null 2>&1"; then
  append_line "OK" "sudo -n доступен (без интерактивного пароля)"
  ((ok+=1))
else
  append_line "FAIL" "sudo -n недоступен; деплой-операции будут блокироваться"
  ((fail+=1))
fi

for svc in caddy docker fail2ban; do
  if run_remote "systemctl is-active ${svc} >/dev/null 2>&1"; then
    append_line "OK" "systemd: ${svc} active"
    ((ok+=1))
  else
    append_line "WARN" "systemd: ${svc} не active"
    ((warn+=1))
  fi
done

for path in /opt/kb-ring /opt/tg_digest_system /opt/server-docs /opt/monitoring; do
  if run_remote "test -e ${path}"; then
    append_line "OK" "Путь существует: ${path}"
    ((ok+=1))
  else
    append_line "WARN" "Путь отсутствует: ${path}"
    ((warn+=1))
  fi
done

if run_remote "test -f /etc/caddy/Caddyfile"; then
  if run_remote "sudo -n caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1"; then
    append_line "OK" "Caddyfile валиден"
    ((ok+=1))
  else
    append_line "WARN" "Caddyfile найден, но validate вернул ошибку"
    ((warn+=1))
  fi
else
  append_line "FAIL" "Caddyfile отсутствует: /etc/caddy/Caddyfile"
  ((fail+=1))
fi

if run_remote "test -d /opt/transcription"; then
  append_line "WARN" "/opt/transcription существует (ожидалось удаление перед новым деплоем)"
  ((warn+=1))
else
  append_line "OK" "/opt/transcription отсутствует (чистое состояние)"
  ((ok+=1))
fi

FREE_DISK_KB="$(run_remote "df -Pk / | awk 'NR==2{print \$4}'" || echo 0)"
if [[ "${FREE_DISK_KB}" =~ ^[0-9]+$ ]] && (( FREE_DISK_KB > 5 * 1024 * 1024 )); then
  append_line "OK" "Свободное место на / > 5GB"
  ((ok+=1))
else
  append_line "WARN" "Мало места на / (free_kb=${FREE_DISK_KB})"
  ((warn+=1))
fi

cat >> "${REPORT_FILE}" <<EOF

## Server Snapshot

\`\`\`
$(run_remote "echo host=\$(hostname); echo whoami=\$(whoami); uptime -p; free -h | sed -n '1,3p'; df -h / | sed -n '1,2p'; docker ps --format '{{.Names}} {{.Status}}' | sed -n '1,20p'" 2>/dev/null || true)
\`\`\`

## Result

- ok=${ok}
- warn=${warn}
- fail=${fail}
EOF

if (( fail > 0 )); then
  echo "Preflight FAIL: ${REPORT_FILE}"
  exit 1
fi

echo "Preflight OK: ${REPORT_FILE}"
