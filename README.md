# KB-RING

KB-RING — единый сервис корпоративных знаний: ингест (загрузка) источников, индексация, поиск, чат/RAG и (позже) связывание сущностей.

Этот репозиторий создаётся как “новый проект”, но намеренно опирается на существующие наработки:
- модель идентификации как в TG Digest System (JWT в `auth_token`, `sub = user_id`);
- PostgreSQL + pgvector как единое хранилище;
- практики “ops-пакета” и повторяемого деплоя.

## Ключевые документы (что считаем источником требований)

Локальные файлы (shared_vm):
- `Единая система знаний ТЗ.txt` — целевая архитектура KB-RING (слои op/tac/arc, инкрементальность, FTS + векторный поиск).
- `запросы по kb.txt` — требования к чат-режиму поверх базы (режимы search-only/rag, hybrid retrieval).
- `Ответы системы.txt` — требования к строгому RAG Answer (обязательные citations, лимиты контекста, без выдумок).

Сводка ограничений по RAG: `kb_ring/docs/ТРЕБОВАНИЯ_RAG.md`.

## Архитектура (на сегодня)

Компоненты:
- **API** (`kb_ring/api/`): FastAPI, входная точка `kb_ring/api/kb_ring/main.py`.
- **Worker** (`kb_ring/worker/`): фоновая обработка `op.jobs` (чанклинг + FTS + локальные embeddings).
- **БД** (`kb_ring/db/`): PostgreSQL + pgvector.

Пока это “скелет”, чтобы начать переписывать TG и transcription как части единого сервиса знаний.

## Модель данных

### Схемы
- `op` — оперативный слой (ingest/курсор/джобы).
- `tac` — тактический слой (документы знаний, чанки, эмбеддинги).
- `chat` — чат/сессии/история + citations.

### Таблицы (минимум)
- `op.jobs`: очередь работ (`queued|running|done|error`).
- `tac.documents`: документ знаний (текст + метаданные + `uri` как каноническая ссылка на источник).
- `tac.chunks`: чанки + `tsvector` для FTS.
- `tac.embeddings`: pgvector (локальные embeddings sentence-transformers, `vector(384)`).
- `chat.sessions`, `chat.messages`, `chat.message_citations`, `chat.session_memory`: чат и источники ответов.

Базовая схема: `kb_ring/db/schema.sql`  
Миграции: `kb_ring/db/migrations/`

## Авторизация (как в TG)

Текущее правило:
- токен берём из cookie `auth_token` или `Authorization: Bearer ...`;
- JWT подписан общим `JWT_SECRET`;
- `sub` в токене — это `user_id` (целое число).

Это нужно, чтобы затем без “второй модели пользователей” объединить:
- TG: его `users/user_identities/audit_log`;
- transcription: все задания/результаты и индексы хранить с привязкой к `user_id`.

## API (этап 0/1)

Базовые эндпоинты:
- `GET /health` — healthcheck (проверка живости).
- `GET /ui` — минимальный UI (вкладка **ПОИСК** + **INGEST**).
- `POST /api/v1/ingest/transcript` — сохранить транскрипт в БД и поставить задачу индексации.
- `GET /api/v1/search?q=...` — FTS поиск по `tac.chunks` (без LLM).

Чат над базой:
- `POST /api/v1/chat/sessions` — создать сессию.
- `GET /api/v1/chat/sessions/{id}` — получить историю.
- `POST /api/v1/chat/sessions/{id}/message` — отправить сообщение:
  - `mode=search`: только retrieval, вернуть результаты (без LLM).
  - `mode=rag`: retrieval -> context -> ChatGPT -> ответ + citations.
  - `mode=analysis`: отчёт/сводка по найденным источникам через ChatGPT (опционально) + citations.

Dev-хелпер (только для локальной отладки):
- `POST /api/v1/dev/login` — выдаёт токен и ставит cookie.

## Локальный запуск

### Вариант A: docker-compose (если совместим)

```bash
cd kb_ring/docker
cp .env.example .env
docker compose up -d --build
```

### Вариант B: без docker-compose (рекомендуется в этой VM)

```bash
kb_ring/scripts/dev_down.sh
kb_ring/scripts/dev_up.sh
```

Проверка:
- API: `http://127.0.0.1:8099/health`
- UI: `http://127.0.0.1:8099/ui`

## Переменные окружения (минимум)

Файл для локальной разработки: `kb_ring/docker/.env` (не коммитится).

- `DATABASE_URL`: строка подключения к Postgres.
- `JWT_SECRET`: общий секрет подписи JWT (должен совпадать у всех сервисов в едином контуре).
- `AUTH_COOKIE_NAME`: по умолчанию `auth_token`.
- `AUTH_COOKIE_DOMAIN`: домен cookie (для SSO по поддоменам на сервере).
- `AUTH_COOKIE_SECURE`: `1/0`, признак `Secure` у cookie.
- `OPENAI_API_KEY`: ключ OpenAI (нужен только для `mode=rag|analysis`).
- `OPENAI_BASE_URL`: базовый URL API (обычно `https://api.openai.com/v1`).
- `OPENAI_MODEL`: модель для ответа (например `gpt-4o-mini`).

Локальные embeddings (по ТЗ; используются для hybrid retrieval, OpenAI embeddings не используются для retrieval):
- `EMBEDDINGS_ENABLED`: `1/0` (по умолчанию `1`).
- `EMBEDDINGS_MODEL`: по умолчанию `sentence-transformers/all-MiniLM-L6-v2`.
- `EMBEDDINGS_DIMS`: по умолчанию `384` (должно совпадать со схемой БД).
- `EMBEDDINGS_BATCH_SIZE`: по умолчанию `32`.

## Миграции БД

В локальном окружении базовая схема создаётся из `kb_ring/db/schema.sql`.

Отдельные миграции лежат в `kb_ring/db/migrations/` и должны применяться к “живой” БД инкрементально.

## Как устроен поиск (этап 1)

- Воркер режет `tac.documents.body_text` на чанки и пишет их в `tac.chunks`.
- Для каждого чанка строится `tsvector` (`to_tsvector('simple', chunk_text)`).
- Для каждого чанка воркер (если установлены зависимости) считает локальные embeddings и пишет их в `tac.embeddings`.
- `GET /api/v1/search` делает hybrid retrieval: FTS + pgvector cosine similarity (если embeddings доступны), иначе FTS-only.

Примечание: индексация embeddings по chunk_sha256 инкрементальная (если чанк не изменился, пересчёт пропускается).

## Как устроен RAG (этап 1)

В `POST /api/v1/chat/sessions/{id}/message` при `mode=rag|analysis`:
1. Выполняется retrieval (hybrid, top-K).
2. Формируется `context` только из top-K чанков (без целых документов).
3. Вызывается ChatGPT/OpenAI.
4. Сохраняется ответ и связи `assistant message -> chunk_id` в `chat.message_citations`.
5. Возвращается JSON: `answer + confidence + citations`.

Ограничения и формат ответа: `kb_ring/docs/ТРЕБОВАНИЯ_RAG.md`.

## Безопасность (минимум)

- Не коммитить `kb_ring/docker/.env` и любые секреты (файл в `.gitignore`).
- В прод-контуре не хранить ключи в репозитории.
- LLM вызывается только в `mode=rag` (search-only должен работать без LLM).

## Примечания по текущему состоянию

- Локальные embeddings используют `sentence-transformers` и требуют установки зависимостей (torch). Если их нет, поиск работает в FTS-only режиме.
- Для работы `mode=rag|analysis` требуется `OPENAI_API_KEY` в `kb_ring/docker/.env` (этот файл в `.gitignore`).
- Вся документация и комментарии в коде ведутся на русском языке (требование проекта).

## План ближайших работ (в рамках переписывания TG + transcription)

1. Единая БД на сервере Нила (Postgres+pgvector) и миграция боевого TG (БД + `telethon.session` + конфиги).
2. Переписать transcription:
   - хранить задания/результаты в `op.*`;
   - хранить документы знаний в `tac.*`;
   - делать индексацию/обогащение как jobs;
   - авторизация только через `auth_token` как в TG.
3. Hybrid retrieval:
   - FTS + pgvector similarity;
   - объединённый скоринг;
   - топ-K чанков для контекста (<=20).
4. UI:
   - полноценная вкладка “ПОИСК”;
   - вкладка “ЧАТ (RAG)” с раскрываемыми citations.
