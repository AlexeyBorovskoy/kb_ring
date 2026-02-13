#!/usr/bin/env bash
set -euo pipefail

docker rm -f kb_ring_api kb_ring_worker kb_ring_postgres >/dev/null 2>&1 || true
echo "Контейнеры kb_ring остановлены."
