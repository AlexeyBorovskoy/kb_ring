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
   - `/tg` TG UI или заменитель (если subpath ломает TG)
   - `/transcription` UI или заменитель (если subpath ломает transcription)
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
- `/tg/*` -> TG UI (strip prefix `/tg`) или заглушка/интеграция в KB-RING
- `/transcription/*` -> transcription UI/API (strip prefix `/transcription`) или заглушка/интеграция в KB-RING

Важно: subpath-проксирование ломает приложения, которые используют абсолютные пути. На шаге 1 допускаем:
- оставить “UI TG” и “UI transcription” как минимум ссылками из портала на отдельные порты внутри (если не хотим поддомены), или
- сделать упрощенные страницы `/tg` и `/transcription` в KB-RING (iframe/redirect), пока не перепишем UI.

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
   - выбрать минимальный набор (например: дайджесты, либо сообщения за N дней)
   - для каждого текста сформировать:
     - `source='tg'`
     - `source_ref='<tg internal id>'`
     - `doc_type='digest'|'message'`
     - `uri='tg://...'` (каноническая ссылка, формат уточнить)
     - `body_text` (текст)
   - поставить `index_document` jobs

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
   - сформировать `uri` вида `kb://transcription/<task_id>` (или другой согласованный формат)
3. Глоссарий обязателен: обеспечить, что применяется до любых LLM postprocess.
4. LLM postprocess (OpenAI) в transcription:
   - либо отключить на шаге 1 (чтобы не было “двойной логики”),
   - либо оставить, но фиксировать промпты и логировать prompt_name, версию и результат.

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

## 8) Открытые вопросы (нужны уточнения)

1. Subpath UI:
   - transcription UI и TG UI под `/transcription` и `/tg` будут работать без правок фронта? Если нет, что выбираем как “проще” на тестовом этапе: заглушки или переписывание UI внутри KB-RING?
2. Импорт TG:
   - есть предпочтительный формат дампа (pg_dump custom/plain)?
   - есть ли требование сохранить “работоспособность TG сервиса” после миграции, или достаточно переноса данных в KB-RING?
3. `uri` формат:
   - для TG: какой канонический формат uri (tg://chat/<id>/msg/<id>?) и будет ли он кликабельным в UI?
   - для transcription: как должен выглядеть кликабельный uri на одном домене?
4. Secrets/ключи:
   - transcription содержит реальные ключи в `.env` слепке. Нужно ли их немедленно ротировать, и кто владелец/где хранятся актуальные значения на сервере?
5. Ресурсы CPU:
   - какие ограничения по CPU/RAM на сервере Нила для bge reranker и e5 embeddings (на корпусе 10–50k)?

