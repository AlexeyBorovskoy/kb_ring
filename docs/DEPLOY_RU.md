# Деплой (черновик)

Цель: развернуть KB-RING как единый сервис знаний на сервере Нила, при этом:
- мигрировать боевой TG Digest System вместе с данными БД и доступами (Telethon session);
- переписать/встроить transcription как источник документов знаний;
- иметь единый вход (как в TG) и единый поиск/чат.

## Принципиальная схема

- Один PostgreSQL + pgvector (единый для всех частей).
- Один Caddy (reverse proxy) с поддоменами:
  - `portal.<ip>.nip.io` (позже: единая точка входа через Яндекс OAuth)
  - `kb.<ip>.nip.io` (UI + API знаний)
  - `tg.<ip>.nip.io` (TG UI, если оставляем отдельным сервисом)
  - `transcription.<ip>.nip.io` (транскрипция, если оставляем отдельным UI)

На этапе 1 допускается упростить:
- оставить один домен `kb.<ip>.nip.io`, а TG/transcription интегрировать как вкладки внутри KB-RING.

## Что переносим из боевого TG (93.77.185.71)

По факту боевого контура:
- docker-compose живёт в `/home/yc-user/tg_digest_system/tg_digest_system/docker`
- контейнеры: `tg_digest_postgres`, `tg_digest_web`, `tg_digest_worker`
- volume-ы:
  - `tg_digest_postgres_data` (Postgres)
  - `tg_digest_worker_data` (внутри лежит `/app/data/telethon.session`)
  - `tg_digest_worker_media`, `tg_digest_worker_logs`
- конфиги/промпты: bind-mount с хоста:
  - `/home/yc-user/tg_digest_system/tg_digest_system/config`
  - `/home/yc-user/tg_digest_system/tg_digest_system/prompts`

Минимальный перенос для сохранения работоспособности TG:
1. Дамп БД `tg_digest`
2. Файл `telethon.session`
3. `config/channels.json` и промпты

## Примечание про секреты

Не хранить реальные секреты в git.
Для сервера держать `.env`/`secrets.env` только на хосте (например `/opt/kb-ring/`), права 600.

## Embeddings + hybrid retrieval (локально, по ТЗ)

Требование: embeddings считаются локально (sentence-transformers), а поиск использует:
- FTS по `tac.chunks.tsv`
- cosine similarity по `tac.embeddings.embedding` (pgvector)

Практика:
- воркер пишет embeddings при индексации документа (по `chunk_sha256`, инкрементально);
- API использует hybrid retrieval там, где доступен эмбеддер; иначе работает в режиме FTS-only.

Переменные окружения (общие для API и worker):
- `EMBEDDINGS_ENABLED=1`
- `EMBEDDINGS_MODEL=sentence-transformers/multilingual-e5-base`
- `EMBEDDINGS_DIMS=768`

Миграции:
- таблица embeddings на `vector(768)` задаётся в `kb_ring/db/migrations/004_e5_embeddings_768.sql`.
  - В текущем виде миграция пересоздаёт `tac.embeddings` (если нужно без потерь данных, миграцию надо адаптировать).

Индексы pgvector:
- создаётся `ivfflat` индекс под cosine ops; для качества/скорости на больших объёмах потребуется тюнинг (lists/probes) и `ANALYZE`.
