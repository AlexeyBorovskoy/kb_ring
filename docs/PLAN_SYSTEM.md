# KB-RING: Сводный План Создания Системы

Дата: 2026-02-13

Цель: единый сервис корпоративных знаний, который объединяет существующие контуры TG Digest и transcription, и обеспечивает:
- ingest источников
- инкрементальную индексацию (chunk/embeddings/NER)
- hybrid retrieval (FTS + pgvector + rerank)
- инженерный RAG (rag-tech) со строгими citations
- единый вход (portal_auth + JWT cookie) и единый домен

Источник требований: документы shared_vm + `docs/LOCAL_AI_CPU_ONLY.md`, `docs/ТРЕБОВАНИЯ_RAG.md`.

## 1) Целевая архитектура (в общем виде)

Единый домен:
- `kb.<ip>.nip.io`
- один “портал” (главная страница) с логином через Yandex OAuth и выбором раздела
- сервисы доступны по путям: `/kb`, `/tg`, `/transcription` (UI должен работать под subpath уже на шаге 1)

Компоненты:
1. Portal/Auth (portal_auth)
   - Yandex OAuth
   - выдача JWT (HS256)
   - установка cookie `auth_token`
2. KB-RING API + UI
   - `/kb/ui`, `/kb/api/...`
   - поиск, чат (search/rag/analysis/rag-tech)
3. Worker (jobs)
   - chunking + FTS
   - embeddings E5 (768) -> `tac.embeddings`
   - NER regex -> `tac.entities`, `tac.chunk_entities`
4. PostgreSQL + pgvector
   - одна БД `kb_ring`
   - внутри: `op.*`, `tac.*`, `chat.*` + импорт схемы/данных TG
5. Transcription (адаптированный)
   - принимает JWT
   - готовый Markdown пушит в KB-RING через `/api/v1/ingest/transcript`
   - канонический кликабельный `uri` для результатов: ссылка на `/transcription/...` на одном домене
6. TG Digest (миграция данных + дальнейшая интеграция)
   - на этапе 1 импортируем “всё” в БД `kb_ring` (структуру менять разрешено)
   - на этапах далее переводим TG данные в модель `tac.documents` (или создаем вьюхи/ETL)
   - канонический кликабельный `uri` для TG: web URL через портал (на нашем домене)

## 2) Данные и потоки

Целевая модель знаний:
- `tac.documents`: нормализованный документ (body_text, uri, meta, source/source_ref)
- `tac.chunks`: чанки + FTS (tsvector)
- `tac.embeddings`: E5 embeddings (768) + chunk_sha256
- `tac.entities`, `tac.chunk_entities`: NER слой
- `chat.*`: сессии/сообщения/citations

Пайплайн (ingest -> index):
1. ingest документа (любой источник)
   - сохранить в `tac.documents`
   - поставить job `index_document` (op.jobs)
2. worker index_document
   - chunking (инкрементально)
   - FTS tsvector
   - embeddings E5 (инкрементально по chunk_sha256)
   - NER regex (и запись связей)

Поиск:
- retrieval topN=50: FTS + vector similarity (pgvector cosine)
- rerank topM=15: `BAAI/bge-reranker-base` (CPU)

Чат:
- `search`: retrieval-only (без LLM)
- `rag`: краткий инженерный ответ + citations
- `analysis`: отчёт/сводка по источникам + citations
- `rag-tech`: строгий инженерный отчёт (таблица + разделы) + citations
  - LLM: OpenAI (если включён), иначе допускается Ollama fallback для черновика

## 3) Интеграция transcription (целевой принцип)

Требования:
- качество документов зависит от глоссария и корректной постобработки
- transcription должен:
  1) строго применять глоссарий
  2) генерировать Markdown артефакты (protocol/summary/tasks/raw)
  3) пушить готовый Markdown в KB-RING (`/api/v1/ingest/transcript`)
  4) прикладывать `source_ref` (task_id) и `uri` (каноническая ссылка на место хранения результата/страницу)

Стратегия:
- на этапе 1: минимальная адаптация под JWT + push в KB-RING
- OpenAI postprocess в transcription НЕ отключаем; фиксируем и версионируем промпты/постобработку (как минимум: имя промпта, хэш/версия текста промпта, модель)
- далее: вынести postprocessing и промпты в KB-RING (или сделать shared prompts), чтобы требования “как формировать документы” были едиными

## 4) Интеграция TG Digest (целевой принцип)

Этап 1:
- создать новую БД `kb_ring`
- импортировать в неё все данные TG (боевой контур: 93.77.185.71), допускается менять структуру
- восстановить TG в отдельную схему `tg.*` внутри `kb_ring`
- сохранить работоспособность TG сервиса после миграции (продолжить ingest/digest на новом сервере)
- в процессе миграции добавить ещё несколько чатов (источников) и убедиться, что они тоже ingest-ятся
- не потерять telethon session/конфиги/медиа

Этап 2+:
- сделать явный мост “TG данные -> документы знаний”:
  - или ETL: материализуем сообщения/дайджесты в `tac.documents` (source=tg)
  - или view-layer: формируем представление и индексируем уже в tac.*
- включить единый auth и единый UI (портал)

## 5) Нефункциональные требования (срез)

- CPU-only AI стек (embeddings + rerank + NER) должен работать на корпусе 10–50k документов
- бюджет по ресурсам: суммарно не более ~30% ресурсов сервера (CPU/RAM) под embeddings/rerank/worker нагрузку
- LLM API не используется для индексации
- любой инженерный ответ содержит citations (chunk_id + uri + score)
- контекст: <= 20 чанков
- инкрементальная индексация: unchanged -> skip

Мониторинг:
- нужен контроль ресурсов и статусов сервисов “типа Zabbix” (CPU/RAM/disk, latency API, очередь jobs, ошибки воркера)

## 6) Этапы реализации (предложение)

Этап 1 (вертикаль под тестовый контур на сервере Нила):
- единый домен + portal_auth
- KB-RING поднят (db+api+worker)
- transcription адаптирован (JWT + push)
- TG данные импортированы в БД kb_ring
- KB-RING индексирует документы из transcription и из TG (как минимум: материализация базового набора документов)
- `rag-tech` работает с citations

Этап 2 (укрепление):
- инкрементальные коннекторы ingest (Nextcloud/GitLab/Kaiten)
- бенчмарки Recall@K, latency, доля корректных citations
- улучшение NER (ruBERT опционально)
- стабилизация UI (таблица citations, фильтры, источники)

## Открытые вопросы (нужны уточнения)

1. Для subpath `/tg`: определить минимальный патч TG web (FastAPI), чтобы корректно работали ссылки/статика и canonical URLs через портал.
2. OCR на шаге 1 для “всех вложений”: какой движок и какие форматы действительно обязательны для MVP, чтобы уложиться в ресурсный бюджет.
3. Enforcement лимита ~30% ресурсов: какие механизмы используем (docker limits vs ограничения параллелизма на уровне воркеров/очередей).
