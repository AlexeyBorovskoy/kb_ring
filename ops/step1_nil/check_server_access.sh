#!/usr/bin/env bash
set -euo pipefail

# Quick access + prerequisites check for Step 1 migration.
#
# Usage:
#   bash kb_ring/ops/step1_nil/check_server_access.sh
#   NIL_SSH=vps-ripas-229 TG_SSH=yc-user@93.77.185.71 bash kb_ring/ops/step1_nil/check_server_access.sh

NIL_SSH="${NIL_SSH:-vps-ripas-229}"
TG_SSH="${TG_SSH:-yc-user@93.77.185.71}"
TG_STACK_DIR="${TG_STACK_DIR:-/home/yc-user/tg_digest_system/tg_digest_system/docker}"

ok=0
warn=0
fail=0

print_result() {
  local status="$1"
  local msg="$2"
  printf '%-8s %s\n' "${status}" "${msg}"
}

echo "[1/2] Checking Nil server (${NIL_SSH})"
if nil_out="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${NIL_SSH}" '
  set -e
  echo "host=$(hostname)"
  echo "whoami=$(whoami)"
  test -d /opt/transcription && echo "transcription=ok" || echo "transcription=missing"
  test -d /opt/tg_digest_system && echo "tg_target=ok" || echo "tg_target=missing"
  test -f /etc/caddy/Caddyfile && echo "caddyfile=ok" || echo "caddyfile=missing"
  systemctl is-active caddy 2>/dev/null | sed "s/^/caddy_status=/" || true
' 2>/dev/null)"; then
  print_result "OK" "SSH to Nil server is available"
  echo "${nil_out}" | sed 's/^/  /'
  ((ok+=1))
  if echo "${nil_out}" | grep -q "tg_target=missing"; then
    print_result "WARN" "/opt/tg_digest_system not found on Nil (must be created before TG deploy)"
    ((warn+=1))
  fi
else
  print_result "FAIL" "Cannot connect to Nil server (${NIL_SSH})"
  ((fail+=1))
fi

echo
echo "[2/2] Checking TG source server (${TG_SSH})"
if tg_out="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${TG_SSH}" "
  set -e
  echo host=\$(hostname)
  echo whoami=\$(whoami)
  test -d '${TG_STACK_DIR}' && echo tg_stack=ok || echo tg_stack=missing
  if test -d '${TG_STACK_DIR}'; then
    cd '${TG_STACK_DIR}'
    test -f docker-compose.yml && echo compose=ok || echo compose=missing
    docker compose ps --format '{{.Name}}:{{.State}}' 2>/dev/null || true
  fi
" 2>/dev/null)"; then
  print_result "OK" "SSH to TG source server is available"
  echo "${tg_out}" | sed 's/^/  /'
  ((ok+=1))
  if echo "${tg_out}" | grep -q "tg_stack=missing"; then
    print_result "FAIL" "TG stack directory not found (${TG_STACK_DIR})"
    ((fail+=1))
  fi
else
  print_result "FAIL" "Cannot connect to TG source server (${TG_SSH})"
  ((fail+=1))
fi

echo
echo "Summary: ok=${ok} warn=${warn} fail=${fail}"
if [[ "${fail}" -gt 0 ]]; then
  exit 1
fi

