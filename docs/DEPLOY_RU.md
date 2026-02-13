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

