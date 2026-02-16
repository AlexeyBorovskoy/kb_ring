# KB-RING: Деплой и Проверка (Runbook)

Дата актуализации: 2026-02-16

Документ описывает практический порядок действий для тестового развертывания и проверки готовности перед деплоем на сервер Нила.

## 1. Принципы выполнения

1. Сначала локальная подготовка, потом сервер.
2. Никакого деплоя без явной команды владельца проекта.
3. Все секреты только на сервере, не в git.
4. Любое изменение на сервере должно быть воспроизводимо через скрипты/документы из репозитория.

## 2. Целевая топология шага 1

- Один домен (single FQDN), единая точка входа.
- Path routing:
  - `/kb` -> KB-RING
  - `/tg` -> TG web
  - `/transcription` -> transcription web
- Единая БД `kb_ring` (postgres + pgvector):
  - `op/tac/chat` для KB-RING
  - `tg` для восстановленного слоя TG

## 3. Что должно быть готово локально

Папка `ops/step1_nil/`:
- `docker-compose.kb_ring.yml`
- `Caddyfile.kb_single_domain.snippet`
- `check_server_access.sh`
- `prepare_nil_layout.sh`
- `restore_tg_dump_to_kb_ring.sh`
- `patch_tg_subpath.sh`
- `patch_transcription_subpath.sh`

Экспорты в `server_exports/`:
- TG: дамп `-Fc`, служебные артефакты.
- Nil: конфиги и рабочие данные (по согласованному списку).

## 4. Серверные пути (для шага 1)

- TG-стек: `/opt/tg_digest_system/`
- KB-RING: `/opt/kb-ring/`
- Секреты:
  - `/opt/tg_digest_system/.../secrets.env`
  - `/opt/kb-ring/secrets.env`

## 5. Миграция TG в `kb_ring`

1. Подготовить/проверить `pg_dump -Fc`.
2. Поднять postgres с `pgvector`.
3. Создать БД `kb_ring`.
4. Восстановить дамп в `tg` схему.
5. Проверить количество строк и ключевые таблицы.
6. Убедиться, что TG runtime артефакты (session/config/prompts) сохранены.

Рекомендуемый инструмент:
- `ops/step1_nil/restore_tg_dump_to_kb_ring.sh`

## 6. Подготовка subpath

### 6.1 TG (`/tg`)

- Базовый подход: FastAPI `root_path=/tg` + корректировка ссылок/статики.
- На первом этапе допускается минимальный патч “как проще”, если UI стабилен.

Инструмент:
- `ops/step1_nil/patch_tg_subpath.sh`

### 6.2 transcription (`/transcription`)

- Допускаются правки `index.html`.
- Все фронтовые API вызовы должны работать через `/transcription/...`.

Инструмент:
- `ops/step1_nil/patch_transcription_subpath.sh`

## 7. OCR политика шага 1

- Primary: `OCR.space`.
- Fallback: `tesseract`.
- Модель очереди: последовательная отправка OCR задач.
- Минимальный форматный набор:
  - `pdf` (включая сканы)
  - `jpg/png`
  - `docx`
  - `txt/md/html`

## 8. Проверка сервиса до решения о деплое

### 8.1 Технический smoke

1. Health:
- API жив
- worker жив
- postgres жив

2. Auth:
- JWT cookie принимается всеми нужными сервисами.

3. Ingest:
- transcription публикует markdown в KB-RING.
- TG данные доступны после restore.

4. Index:
- создаются chunks/embeddings.

5. Search/RAG:
- `search` возвращает результаты
- `rag-tech` возвращает citations

6. OCR:
- на тестовом наборе форматов text extraction проходит

### 8.2 Нагрузочная sanity-проверка

- проверить, что при индексации лимиты worker/api удерживают нагрузку в согласованных пределах.
- проверить, что latency API не деградирует до нерабочего уровня.

## 9. Мониторинг (zabbix-like)

Минимум контролируемых сигналов:
- host CPU/RAM/Disk
- DB connection pressure
- API latency/error
- worker queue depth/error
- TG/transcription service status
- OCR error rate / timeout rate

Если полноценный Zabbix сервер недоступен, допускается временный аналог с сопоставимым покрытием метрик.

## 10. Откат и безопасность

- Перед изменениями хранить backup конфигов/дампов.
- Секреты не выводить в логи и не коммитить.
- При деградации:
  - вернуть прошлую конфигурацию прокси;
  - остановить новые сервисы;
  - восстановить прежний рабочий маршрут.

## 11. Финальный отчёт перед деплоем

Перед запросом на деплой фиксируется отчёт:
1. Список выполненных проверок.
2. Что прошло и что не прошло.
3. Остаточные риски.
4. Готовность к запуску на Ниле.

Этот отчёт является обязательным входом для решения “деплоить / не деплоить”.
