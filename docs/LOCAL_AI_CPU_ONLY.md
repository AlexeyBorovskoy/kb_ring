# CPU-only локальный AI-стек (E5 + BGE + NER + Ollama)

Источник требований: `/home/alexey/shared_vm/использование локальной ИИ.txt`.

## Выбранный стек

- Embeddings: `sentence-transformers/multilingual-e5-base` (768 dims) в `tac.embeddings.embedding vector(768)`.
- Reranker: `BAAI/bge-reranker-base` (cross-encoder), применяется в runtime (не в индексации).
- NER: regex (обязательный слой) + (опц.) модель ruBERT NER.
- Local LLM (опц.): Ollama 7B Q4, используется только как fallback для черновиков.

## Текущий статус в репозитории

- Embeddings (E5, 768 dims): реализовано.
- Hybrid retrieval (FTS + pgvector): реализовано.
- Reranker (BGE): реализовано (CPU).
- NER regex + сохранение в БД: реализовано.
- Режим `rag-tech`: реализовано (retrieval+rerank, citations обязательны, Ollama fallback при отсутствии OpenAI).
- Бенчмарки: добавлены минимальные скрипты в `kb_ring/scripts/`.

## Миграции

- `kb_ring/db/migrations/004_e5_embeddings_768.sql`
- `kb_ring/db/migrations/005_entities.sql`

## Переменные окружения

- `EMBEDDINGS_ENABLED=1`
- `EMBEDDINGS_MODEL=sentence-transformers/multilingual-e5-base`
- `EMBEDDINGS_DIMS=768`
- `RERANK_ENABLED=1`
- `RERANK_MODEL=BAAI/bge-reranker-base`
- `RERANK_TOP_N=50`
- `RERANK_TOP_M=15`
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=mistral:7b-instruct-q4_K_M`

## Примеры

Через UI: вкладка `CHAT (RAG)` и mode `rag-tech`.

Через curl:

```bash
curl -s -X POST 'http://127.0.0.1:8099/api/v1/dev/login' -d 'user_id=1' -c /tmp/kb.cookie >/dev/null
curl -s -X POST 'http://127.0.0.1:8099/api/v1/chat/sessions' -d 'title=ui' -b /tmp/kb.cookie
curl -s -X POST 'http://127.0.0.1:8099/api/v1/chat/sessions/1/message' -d 'text=Дай описание и примеры интерфейсов АСУДД' -d 'mode=rag-tech' -b /tmp/kb.cookie
```

