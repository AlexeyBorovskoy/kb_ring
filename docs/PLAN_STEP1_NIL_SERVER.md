# План Шага 1: Развертывание На Сервере Нила + Миграция TG + Интеграция Transcription

Дата: 2026-02-13

Цель шага 1 (DoD):
- единый домен `kb.<ip>.nip.io` (без поддоменов), главная страница + login через Yandex OAuth (portal_auth)
- KB-RING поднят через docker-compose: `postgres(pgvector) + api + worker`
- создана новая БД `kb_ring`, в которую импортированы данные TG digest с боевого сервера `93.77.185.71` (разрешено менять структуру)
- transcription адаптирован: JWT + push готового Markdown в KB-RING (`/api/v1/ingest/transcript`)
- KB-RING индексирует и ищет по данным transcription и TG (hybrid retrieval + rerank)
- `rag-tech` работает и возвращает citations (chunk_id + uri + score)

## 0) Предпосылки/ограничения

1. Один FQDN (пример): `kb.89.124.65.229.nip.io`
2. Пути сервисов:
   - `/` портал
   - `/kb` KB-RING UI/API
   - `/tg` TG UI (под subpath на шаге 1)
   - `/transcription` transcription UI (под subpath на шаге 1)
3. Secrets не хранятся в git: единый `secrets.env` на сервере

## 1) Дерево каталогов на сервере (предложение)

- `/opt/kb-ring/`
  - `docker-compose.yml`
  - `secrets.env` (600)
  - `data/`
    - `pg/` (volume или bind, если нужно)
    - `imports/` (дампы TG)
    - `telethon/` (telethon.session если переносим)
    - `tg_config/` (channels.json/prompts)

- `/opt/portal-auth/` (если отдельным сервисом)
- `/opt/transcription/` (уже существует; адаптируем)

## 2) Сеть и reverse proxy (Caddy)

Цель: один site block `kb.<ip>.nip.io`.

Роутинг (проектно):
- `/` -> portal_auth (главная + login)
- `/kb/*` -> KB-RING API/UI (strip prefix `/kb`)
- `/tg/*` -> TG UI (strip prefix `/tg`)
- `/transcription/*` -> transcription UI/API (strip prefix `/transcription`)

Важно: на шаге 1 subpath обязателен. Значит:
- TG и transcription нужно пропатчить под работу “за префиксом” (base_url/root_path), чтобы ссылки и статика работали корректно.

## 3) Авторизация (portal_auth + JWT)

Обязательное на шаге 1:
- portal_auth (Yandex OAuth) выдает JWT (HS256)
- cookie: `auth_token=<jwt>` на домене `kb.<ip>.nip.io` (path `/`, httpOnly)
- KB-RING API проверяет JWT из cookie/Authorization
- transcription (после адаптации) проверяет JWT из cookie/Authorization
- TG (если UI живет отдельно) либо:
  - принимает общий JWT, либо
  - используется только как источник данных (без UI), тогда auth в TG UI можно отложить

## 4) База данных: новая `kb_ring` + импорт TG

### 4.1 Создание БД и расширений

- поднять `pgvector/pgvector` контейнер
- создать базу `kb_ring`
- применить KB-RING схему/миграции:
  - `db/schema.sql` (для dev) или миграции `db/migrations/*.sql` (для “живой” БД)

### 4.2 Импорт данных TG из боевого контура (93.77.185.71)

Минимальный перенос (чтобы “не потерять” и можно было продолжить):
- дамп БД TG digest
- `telethon.session`
- `config/channels.json`, `prompts/`
- `media/` (если нужно)

Стратегия импорта в одну БД `kb_ring` (рекомендуемый минимум для шага 1):
1. Восстановить дамп TG в отдельную схему внутри `kb_ring` (например `tg.*`), чтобы избежать конфликтов с `op/tac/chat`.
2. Добавить слой материализации в `tac.documents`:
   - материализовать ВСЕ: дайджесты, сообщения, вложения (pdf/docx/и т.п. где есть текст/извлечение)
   - для каждого текста сформировать:
     - `source='tg'`
     - `source_ref='<tg internal id>'`
     - `doc_type='digest'|'message'`
     - `uri` кликабельный web URL через портал (на нашем домене)
     - `body_text` (текст)
   - поставить `index_document` jobs

Требование: после миграции TG сервис должен остаться работоспособным, и в процессе миграции нужно добавить ещё несколько чатов в ingest.

Примечание: структура TG может меняться (разрешено), но на шаге 1 лучше минимизировать изменения и сделать “слой интеграции” через ETL.

## 5) KB-RING: docker-compose (db + api + worker)

Цель:
- один compose-проект `/opt/kb-ring`
- env в `secrets.env`
- api и worker используют одинаковые параметры embeddings/rerank/NER

Минимальные env:
- `DATABASE_URL=postgresql://.../kb_ring`
- `JWT_SECRET=...` (общий для portal_auth + KB-RING + transcription)
- `AUTH_COOKIE_NAME=auth_token`
- `AUTH_COOKIE_DOMAIN=` (скорее пусто для single FQDN, уточнить)
- `AUTH_COOKIE_SECURE=1`

CPU-only AI стек:
- `EMBEDDINGS_MODEL=sentence-transformers/multilingual-e5-base`
- `EMBEDDINGS_DIMS=768`
- `RERANK_MODEL=BAAI/bge-reranker-base`
- `RERANK_TOP_N=50`
- `RERANK_TOP_M=15`

LLM режимы:
- OpenAI ключ можно включать/выключать (для rag/analysis)
- `rag-tech` допускает Ollama fallback

## 6) Transcription: адаптация под шаг 1

Текущее состояние на сервере (по слепку):
- systemd service слушает `127.0.0.1:8081`
- Caddy проксирует `transcription.<ip>.nip.io -> 127.0.0.1:8081` (это будет заменено на path routing под `kb.<ip>.nip.io`)
- сервис хранит результаты в `results/<task_id>.md`, глоссарий в `data/glossary.txt`, промпты в `data/prompts/*.txt`

Изменения на шаге 1:
1. Добавить JWT auth (cookie/Authorization) на API transcription.
2. После формирования Markdown результата вызвать KB-RING:
   - `POST /api/v1/ingest/transcript`
   - передать `title`, `text` (Markdown), `source_ref=transcription:task_id=<uuid>`
   - сформировать кликабельный `uri` вида `https://kb.<ip>.nip.io/transcription/...` (конкретный URL результата)
3. Глоссарий обязателен: обеспечить, что применяется до любых LLM postprocess.
4. LLM postprocess (OpenAI) в transcription:
   - НЕ отключать на шаге 1
   - фиксировать промпты и версии: имя промпта, хэш/версия текста промпта, модель (`OPENAI_GPT_MODEL`), время обработки

## 7) Индексация и проверки

Проверки после разворачивания:
1. Авторизация:
   - login через portal_auth
   - `/kb/health` и `/kb/ui` доступны только с JWT
2. Transcription push:
   - загрузить аудио, дождаться результата
   - KB-RING получил документ и поставил job
3. Worker:
   - создал chunks, embeddings, entities
4. Поиск:
   - `/kb/api/v1/search?q=...` возвращает результаты
   - hybrid retrieval активен (есть vec_score)
5. rag-tech:
   - `/kb/api/v1/chat/... mode=rag-tech` возвращает ответ и citations

## 8) Мониторинг (типа Zabbix)

Требование: контроль ресурсов и работоспособности в тестовом контуре, при этом AI нагрузка должна укладываться в ~30% ресурсов сервера.

Минимум метрик/триггеров:
- CPU/RAM/disk (host)
- postgres: connections, locks, size, slow queries (минимально)
- KB-RING API: latency 95p, error rate
- Worker: размер очереди `op.jobs` (queued/running/error), скорость индексации (chunks/min), ошибки
- TG ingest/digest: статус сервисов, лаг по последним сообщениям
- transcription: статус systemd, очередь задач/ошибки

Инструмент:
- либо Zabbix Agent(2) на сервере + внешний Zabbix server,
- либо “заменитель” уровня netdata/Prometheus-node-exporter с алертами (если Zabbix server отсутствует).

## 9) Открытые вопросы (нужны уточнения)

1. Subpath для TG (FastAPI): где точка входа/настройка `root_path`/base_url, чтобы `/tg` работал без ломания статики и ссылок?
2. OCR для вложений: используем cloud OCR ключи из TG стека. Обработка строго последовательная (один объект -> ответ -> следующий), с таймаутами и ретраями.
3. Форматы MVP на шаге 1: `pdf (включая сканы)`, `jpg/png`, `docx`, `txt/md/html`.
4. Лимит ресурсов: enforce “не более 30% ресурсов сервера” через docker limits (cpu/mem) + ограничение параллелизма в embeddings/rerank/OCR.
