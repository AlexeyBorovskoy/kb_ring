# Server Access Check (2026-02-16)

Проверено: понедельник, **16 февраля 2026**.

## Nil (89.124.65.229)

- Рабочий доступ: `alexey@89.124.65.229` (алиас `vps-ripas-229`) — OK.
- `root@89.124.65.229` — denied (publickey/password).
- Каталоги:
  - `/opt/transcription` — OK
  - `/opt/tg_digest_system` — отсутствует (нужно создать перед выкладкой TG)
- Caddy:
  - `/etc/caddy/Caddyfile` — OK
  - `systemctl is-active caddy` — `active`

## TG Source (93.77.185.71)

- Рабочий доступ: `yc-user@93.77.185.71` — OK.
- Стек TG:
  - путь ` /home/yc-user/tg_digest_system/tg_digest_system/docker` — OK
  - `docker-compose.yml` — OK
  - контейнеры `postgres`, `web`, `worker` — `Up (healthy)`

## Вывод

- Доступы для миграции подтверждены.
- Блокер только один: на Ниле нужно создать целевой путь `/opt/tg_digest_system`.
- Для проверки перед выкладкой используем:
  - `ops/step1_nil/check_server_access.sh`
  - `ops/step1_nil/prepare_nil_layout.sh`

