# Nil: Start-Deploy Preparation

Дата: 2026-02-16

Документ фиксирует минимально необходимую подготовку перед фактическим деплоем KB-RING на сервер Нила с учетом правил из:
- `ADMIN_GUIDE.md`
- `logbook.md`
- `maintenance-rules.md`

## 1) Что обязательно перед деплоем

1. Проверить текущее состояние сервера и сервисов.
2. Сделать резервные копии ключевых конфигов перед изменениями.
3. Обновить `/opt/server-docs/logbook.md` записью о подготовке.
4. Подтвердить, что старый transcription-контур снят (если принято такое решение).
5. Подтвердить наличие директорий деплоя `/opt/kb-ring` и `/opt/tg_digest_system`.

## 2) Готовые скрипты

- `ops/step1_nil/preflight_nil_deploy_start.sh`
  - читает состояние Нила и генерирует локальный отчет `ops/step1_nil/reports/preflight_<ts>.md`
  - валидирует SSH/sudo/systemd/caddy/пути/свободное место

- `ops/step1_nil/prepare_nil_deploy_start.sh`
  - делает backup в `/opt/backups/kb_ring_deploy_start_<ts>`
  - готовит каталоги `/opt/kb-ring`, `/opt/tg_digest_system`
  - добавляет запись в `/opt/server-docs/logbook.md`

## 3) Порядок запуска

```bash
NIL_SSH=vps-ripas-229 bash ops/step1_nil/preflight_nil_deploy_start.sh
NIL_SSH=vps-ripas-229 bash ops/step1_nil/prepare_nil_deploy_start.sh
```

## 4) Критерии "готовы к началу деплоя"

1. Последний preflight без `FAIL`.
2. backup-каталог создан на Ниле и содержит копии ключевых конфигов.
3. В `logbook.md` добавлена запись о подготовке.
4. Старый transcription удален и не активен.
5. Команда проекта подтверждает переход к шагу применения compose/caddy/миграции.
