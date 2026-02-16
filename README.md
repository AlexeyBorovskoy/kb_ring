# KB-RING

KB-RING — единая система знаний, которая объединяет TG Digest и transcription в общий контур: общая авторизация, общая БД, единый поиск и инженерный RAG с обязательными citations.

Обновлено: 2026-02-16.

## 1. Текущее состояние проекта

Сделано:
- Подготовлен каркас сервиса `api + worker + postgres(pgvector)`.
- Принято целевое решение по домену: один FQDN, вход через общий портал, сервисы под `subpath`.
- Подготовлен локальный набор `ops/step1_nil/*` для минимальной нагрузки на сервер Нила.
- Подтверждён формат миграции TG: `pg_dump -Fc` (custom) + восстановление в схему `tg` внутри БД `kb_ring`.
- Подтверждена цель шага 1: индексировать данные из TG и transcription в единую модель документов.
- Для OCR в TG-контуре зафиксирован профиль: `OCR.space` как primary + `tesseract` fallback.

В работе (до команды на деплой):
- Финальная локальная валидация полного цикла (`ingest -> index -> search/rag-tech`).
- Подготовка контролируемого запуска на сервере Нила без удаления действующих контуров до отдельного подтверждения.

## 2. Зафиксированные решения

- Один целевой домен (одна главная страница входа).
- Маршрутизация через пути:
  - `/kb` — KB-RING
  - `/tg` — TG web
  - `/transcription` — transcription web
- Шаг 1 выполняется без «большого» рефакторинга TG/transcription: сначала совместимость и миграция, потом оптимизация.
- Новая БД: `kb_ring`, при этом все данные TG должны помещаться в эту БД (схема `tg` + материализация в `tac`).
- Индексация вложений TG на шаге 1: минимум `pdf`, `jpg/png`, `docx`, `txt/md/html`; OCR обязателен.
- Нагрузка AI-процессов ограничивается: не более ~30% ресурсов сервера через docker limits + контроль параллелизма.

## 3. Целевая архитектура

Компоненты:
1. `portal_auth` (Yandex OAuth) — логин и выпуск JWT.
2. `KB-RING API` (`api/kb_ring/main.py`) — ingest, поиск, чат, citations.
3. `KB-RING Worker` (`worker/`) — chunking, embeddings, rerank/NER-пайплайн.
4. `PostgreSQL + pgvector` (`db/`) — единое хранилище `op/tac/chat` + `tg`.
5. `TG Digest` — источник данных и UI под `/tg`.
6. `transcription` — источник markdown-документов под `/transcription`.

Логический поток:
- источник (TG/transcription) -> `tac.documents` -> `op.jobs` -> `tac.chunks` -> `tac.embeddings` -> retrieval/rerank -> ответ с citations.

## 4. Модель данных (минимальный обязательный слой)

Схемы:
- `op` — очередь и служебные процессы.
- `tac` — документы знаний, чанки, эмбеддинги, сущности.
- `chat` — сессии, сообщения, citations.
- `tg` — восстановленная схема и данные TG после миграции.

Ключевые таблицы:
- `op.jobs`
- `tac.documents`
- `tac.chunks`
- `tac.embeddings`
- `tac.entities`, `tac.chunk_entities`
- `chat.sessions`, `chat.messages`, `chat.message_citations`, `chat.session_memory`

Базовая схема: `db/schema.sql`.
Миграции: `db/migrations/`.

## 5. Авторизация и единый вход

- Токен: JWT (HS256).
- Cookie: `auth_token`.
- Источник идентичности: `sub = user_id` (совместимость с TG-подходом).
- Общие секреты задаются только через серверный `secrets.env`, не через git.

## 6. API (этап 0/1)

Базовые эндпоинты:
- `GET /health`
- `GET /ui`
- `POST /api/v1/ingest/transcript`
- `GET /api/v1/search`

Чат:
- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{id}`
- `POST /api/v1/chat/sessions/{id}/message` (`search|rag|analysis|rag-tech`)

Требование: `rag-tech` всегда возвращает citations.

## 7. OCR и извлечение вложений

Для шага 1:
- Primary OCR: `OCR.space`.
- Fallback: локальный `tesseract`.
- Режим загрузки OCR-задач: последовательный (для устойчивости cloud OCR и контроля ресурсов).

Планируемая эволюция:
- HF endpoint допускается как дополнительный OCR/vision backend, но не обязателен для шага 1.

## 8. Локальный запуск

Вариант A:
```bash
cd docker
cp .env.example .env
docker compose up -d --build
```

Вариант B:
```bash
scripts/dev_down.sh
scripts/dev_up.sh
```

Проверка:
- `http://127.0.0.1:8099/health`
- `http://127.0.0.1:8099/ui`

## 9. Что подготовлено для шага 1

Каталог `ops/step1_nil/` содержит:
- compose и Caddy шаблоны;
- проверку доступов к серверам;
- подготовку директорий на сервере Нила;
- восстановление TG дампа `-Fc` в `kb_ring` с ремапом в `tg`;
- патчи для subpath (`/tg`, `/transcription`).

Подробно: `ops/step1_nil/README.md`.

## 10. Критерии готовности шага 1 (DoD)

Шаг 1 считается закрытым, если одновременно выполняются пункты:
1. Единый домен и вход через портал работают.
2. TG и transcription доступны и корректно работают под `subpath`.
3. БД `kb_ring` создана, TG-данные импортированы в схему `tg`.
4. Документы из TG и transcription индексируются в `tac`.
5. Поиск и `rag-tech` возвращают корректные citations.
6. Нагрузка AI-процессов контролируется и не выходит за согласованный бюджет ресурсов.

## 11. Главные документы проекта

- `docs/PLAN_SYSTEM.md` — сводный план всей системы.
- `docs/PLAN_STEP1_NIL_SERVER.md` — подробный план шага 1.
- `docs/DEPLOY_RU.md` — практический runbook деплоя/проверки.
- `docs/LOCAL_AI_CPU_ONLY.md` — локальный AI-стек на CPU.
- `docs/ТРЕБОВАНИЯ_RAG.md` — требования к RAG и формату ответа.
- `ops/step1_nil/README.md` — пакет локальной подготовки и миграции.
