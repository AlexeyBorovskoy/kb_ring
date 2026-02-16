# Step 1 (Nil Server): Local Preparation Pack

Цель: максимально подготовить всё локально, чтобы на сервере Нила выполнить минимум действий:
- развернуть KB-RING (db+api+worker) через docker-compose
- развернуть/подключить portal_auth
- перенести TG Digest (данные + конфиги) в одну БД `kb_ring` в схему `tg.*`
- перевести сервисы под один FQDN `kb.<ip>.nip.io` и subpath `/kb`, `/tg`, `/transcription`

См. также:
- `docs/PLAN_STEP1_NIL_SERVER.md`
- `docs/PLAN_SYSTEM.md`

## Содержимое каталога

- `Caddyfile.kb_single_domain.snippet`
  - единый vhost `kb.<ip>.nip.io` и маршруты по путям
- `docker-compose.kb_ring.yml`
  - compose для `kb_postgres` + `kb_api` + `kb_worker`
- `docker-compose.portal_auth.yml`
  - compose для `portal_auth` (если не хотим systemd)
- `generate_tg_schema_restore_sql.sh`
  - из `pg_dump -Fc` делает SQL-скрипт восстановления в схему `tg` (через `SET search_path`)
- `restore_tg_dump_to_kb_ring.sh`
  - восстанавливает `pg_dump -Fc` в `kb_ring` c ремапом `public.* -> tg.*`
- `tg_etl_placeholder.md`
  - что именно материализуем из `tg.*` в `tac.documents` на шаге 1 (все: сообщения/дайджесты/вложения)
- `check_server_access.sh`
  - проверка SSH-доступа и обязательных путей/сервисов на Ниле и TG сервере
- `prepare_nil_layout.sh`
  - создаёт целевые каталоги `/opt/kb-ring` и `/opt/tg_digest_system` на Ниле
- `patch_tg_subpath.sh`
  - патчит TG web под `/tg` (redirects + frontend absolute links/fetch)
- `patch_transcription_subpath.sh`
  - патчит transcription frontend под `/transcription` (absolute fetch paths)

## Нужные входные данные (уже выгружаем скриптами)

- TG exports: `server_exports/tg_93_77_185_71/...`
  - `tg_digest.dump` (pg_dump -Fc)
  - `telethon.session`
  - `channels.json`, `prompts/`, `.env`, `secrets.env`, `db/schema.sql`, `db/migrations/`

- Nil exports: `server_exports/<timestamp>/...`
  - `/opt/transcription/.env`
  - `/etc/caddy/Caddyfile`
  - `/opt/monitoring/*`, `/opt/server-docs/*`
  - transcription data (`uploads/`, `results/`, `data/`)

## Замечания по нагрузке на сервер

- Индексацию и OCR на шаге 1 запускаем последовательно/ограниченно:
  - docker limits на KB-RING worker/api
  - ограничение параллелизма embeddings/rerank/OCR
- TG media на боевом сейчас порядка нескольких GB. На тестовом шаге 1 допускается:
  - переносить media выборочно, либо
  - переносить целиком (дольше, но проще), затем ETL/индексация уже на Ниле.

## Порядок запуска (минимум)

1. Проверить доступы:
   - `bash kb_ring/ops/step1_nil/check_server_access.sh`
2. Подготовить каталоги на Ниле:
   - `NIL_SSH=vps-ripas-229 bash kb_ring/ops/step1_nil/prepare_nil_layout.sh`
3. Применить subpath-патчи:
   - `WEB_DIR=/opt/tg_digest_system/tg_digest_system/web bash kb_ring/ops/step1_nil/patch_tg_subpath.sh`
   - `TRANSCRIPTION_DIR=/opt/transcription bash kb_ring/ops/step1_nil/patch_transcription_subpath.sh`
4. Восстановить TG dump в `kb_ring`:
   - `DUMP=.../tg_digest.dump DATABASE_URL=postgresql://.../kb_ring bash kb_ring/ops/step1_nil/restore_tg_dump_to_kb_ring.sh`
