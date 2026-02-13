#!/usr/bin/env bash
set -euo pipefail

# Локальный запуск без docker-compose (полезно, когда compose v1 несовместим с новой версией Docker).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_FILE="${ROOT_DIR}/docker/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Не найден ${ENV_FILE}. Создаю из .env.example"
  cp "${ROOT_DIR}/docker/.env.example" "${ENV_FILE}"
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

NETWORK="kb_ring_network"
PG_VOL="kb_ring_postgres_data"

docker network inspect "${NETWORK}" >/dev/null 2>&1 || docker network create "${NETWORK}" >/dev/null
docker volume inspect "${PG_VOL}" >/dev/null 2>&1 || docker volume create "${PG_VOL}" >/dev/null

if ! docker ps --format '{{.Names}}' | grep -qx 'kb_ring_postgres'; then
  docker run -d \
    --name kb_ring_postgres \
    --network "${NETWORK}" \
    --network-alias postgres \
    -e POSTGRES_DB="${POSTGRES_DB:-kb_ring}" \
    -e POSTGRES_USER="${POSTGRES_USER:-kb_ring}" \
    -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-kb_ring_local}" \
    -v "${PG_VOL}:/var/lib/postgresql/data" \
    -v "${ROOT_DIR}/db/schema.sql:/docker-entrypoint-initdb.d/01_schema.sql:ro" \
    -p "127.0.0.1:${POSTGRES_HOST_PORT:-15432}:5432" \
    pgvector/pgvector:pg16 >/dev/null
fi

docker build -t kb_ring_api -f "${ROOT_DIR}/docker/Dockerfile.api" "${ROOT_DIR}" >/dev/null
docker build -t kb_ring_worker -f "${ROOT_DIR}/docker/Dockerfile.worker" "${ROOT_DIR}" >/dev/null

if ! docker ps --format '{{.Names}}' | grep -qx 'kb_ring_api'; then
  docker run -d \
    --name kb_ring_api \
    --network "${NETWORK}" \
    -e DATABASE_URL="${DATABASE_URL:-postgresql://kb_ring:kb_ring_local@postgres:5432/kb_ring}" \
    -e JWT_SECRET="${JWT_SECRET:-}" \
    -e AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME:-auth_token}" \
    -e AUTH_COOKIE_DOMAIN="${AUTH_COOKIE_DOMAIN:-}" \
    -e AUTH_COOKIE_SECURE="${AUTH_COOKIE_SECURE:-0}" \
    -e OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    -e OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}" \
    -e OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}" \
    -e OPENAI_EMBED_MODEL="${OPENAI_EMBED_MODEL:-text-embedding-3-small}" \
    -p "127.0.0.1:8099:8099" \
    kb_ring_api >/dev/null
fi

if ! docker ps --format '{{.Names}}' | grep -qx 'kb_ring_worker'; then
  docker run -d \
    --name kb_ring_worker \
    --network "${NETWORK}" \
    -e DATABASE_URL="${DATABASE_URL:-postgresql://kb_ring:kb_ring_local@postgres:5432/kb_ring}" \
    kb_ring_worker >/dev/null
fi

echo "Запущено:"
echo "  API:  http://127.0.0.1:8099/health"
echo "  Postgres: 127.0.0.1:${POSTGRES_HOST_PORT:-15432}"
