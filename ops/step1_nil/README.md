# Step 1 (Nil Server): Local Preparation Pack

Дата актуализации: 2026-02-16

Назначение: подготовить максимум работ локально, чтобы на сервере Нила выполнить минимальный, контролируемый и обратимый набор действий.

## 1. Что решает этот пакет

- Проверка доступов к Нилу и боевому TG.
- Подготовка целевой структуры каталогов на Ниле.
- Восстановление TG дампа `pg_dump -Fc` в БД `kb_ring` (схема `tg`).
- Подготовка single-domain Caddy маршрутизации с subpath.
- Патч TG/transcription под `/tg` и `/transcription`.
- Базовая доказуемость миграционного сценария до финального деплоя.

## 2. Файлы и назначение

- `Caddyfile.kb_single_domain.snippet`
- Шаблон маршрутизации на одном домене по путям `/kb`, `/tg`, `/transcription`.

- `docker-compose.kb_ring.yml`
- Тестовый compose для `postgres + api + worker`.

- `docker-compose.portal_auth.yml`
- Опциональный compose для portal_auth.

- `check_server_access.sh`
- Проверка SSH-доступа и ключевых путей/сервисов на целевых серверах.

- `prepare_nil_layout.sh`
- Создание базовой структуры каталогов на Ниле.

- `generate_tg_schema_restore_sql.sh`
- Генератор SQL сценария восстановления TG дампа в отдельную схему.

- `restore_tg_dump_to_kb_ring.sh`
- Восстановление `pg_dump -Fc` в `kb_ring` с remap `public -> tg`.

- `patch_tg_subpath.sh`
- Минимальный патч TG web/FastAPI под `/tg`.

- `patch_transcription_subpath.sh`
- Минимальный патч transcription frontend/API под `/transcription`.

- `tg_etl_placeholder.md`
- Концепт ETL: материализация TG данных в `tac.documents`.

- `SERVER_ACCESS_2026-02-16.md`
- Фиксация факта проверки доступа и контекста окружения.

## 3. Быстрый порядок применения

### Шаг A. Проверить доступы

```bash
bash ops/step1_nil/check_server_access.sh
```

Ожидаемый результат:
- доступ к Нилу подтверждён;
- доступ к TG серверу подтверждён;
- ключевые пути читаются.

### Шаг B. Подготовить layout на Ниле

```bash
NIL_SSH=vps-ripas-229 bash ops/step1_nil/prepare_nil_layout.sh
```

Ожидаемый результат:
- существуют `/opt/kb-ring` и `/opt/tg_digest_system`.

### Шаг C. Применить subpath патчи

TG:
```bash
WEB_DIR=/opt/tg_digest_system/tg_digest_system/web bash ops/step1_nil/patch_tg_subpath.sh
```

Transcription:
```bash
TRANSCRIPTION_DIR=/opt/transcription bash ops/step1_nil/patch_transcription_subpath.sh
```

Ожидаемый результат:
- фронт и API пути корректно работают под `/tg` и `/transcription`.

### Шаг D. Восстановить TG дамп в `kb_ring`

```bash
DUMP=/path/to/tg_digest.dump \
DATABASE_URL=postgresql://USER:PASS@HOST:5432/kb_ring \
bash ops/step1_nil/restore_tg_dump_to_kb_ring.sh
```

Ожидаемый результат:
- все TG таблицы/объекты восстановлены в схему `tg`.

## 4. Входные данные

Обязательные:
- TG дамп `pg_dump -Fc`.
- runtime артефакты TG (`telethon.session`, `channels.json`, `prompts/`).
- доступы SSH к Нилу и TG серверу.

Желательные:
- экспорт серверных конфигов и документов в `server_exports/`.

## 5. Проверки после применения

Минимальный чек:
1. TG web открывается под `/tg`.
2. transcription открывается под `/transcription`.
3. TG данные доступны в `kb_ring.tg.*`.
4. KB-RING API может читать и индексировать тестовый документ.
5. OCR сценарий не падает и использует fallback при ошибке primary.

## 6. Ограничения и принципы безопасности

- Скрипты не должны коммитить/печать реальные секреты.
- Любые изменения на сервере фиксировать в журнале действий.
- Без подтверждения владельца проекта деплой не запускать.
- Любой рискованный шаг сначала проверять в тестовом контуре.

## 7. Полезные связанные документы

- `README.md`
- `docs/PLAN_SYSTEM.md`
- `docs/PLAN_STEP1_NIL_SERVER.md`
- `docs/DEPLOY_RU.md`

