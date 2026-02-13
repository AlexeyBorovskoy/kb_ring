-- KB-RING: базовые схемы (op/tac/chat) + pgvector.
-- Этот файл используется как стартовая схема для локальной разработки.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS op;   -- оперативный слой: ingest/джобы/курсор
CREATE SCHEMA IF NOT EXISTS tac;  -- тактический слой: документы/чанки/эмбеддинги
CREATE SCHEMA IF NOT EXISTS chat; -- чат/сессии/история + citations (RAG)

-- -----------------------------------------------------------------------------
-- tac.documents
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tac.documents (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT,
  source TEXT NOT NULL,                 -- tg|transcription|nextcloud|gitlab|kaiten|...
  source_ref TEXT,                      -- стабильный внешний идентификатор/путь/URL
  uri TEXT,                             -- каноническая ссылка (nextcloud://..., gitlab://..., ...)
  doc_type TEXT NOT NULL,               -- transcript|digest|file|note|...
  title TEXT,
  body_text TEXT,                       -- нормализованный полный текст
  meta JSONB NOT NULL DEFAULT '{}',
  content_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tac_documents_user ON tac.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_tac_documents_source_ref ON tac.documents(source, source_ref);
CREATE INDEX IF NOT EXISTS idx_tac_documents_uri ON tac.documents(uri);

-- -----------------------------------------------------------------------------
-- tac.chunks (FTS)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tac.chunks (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES tac.documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_sha256 TEXT,
  tsv tsvector,
  meta JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_tac_chunks_doc ON tac.chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_tac_chunks_tsv ON tac.chunks USING GIN (tsv);

-- -----------------------------------------------------------------------------
-- tac.embeddings (pgvector, локальные embeddings E5)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tac.embeddings (
  id BIGSERIAL PRIMARY KEY,
  chunk_id BIGINT NOT NULL REFERENCES tac.chunks(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  dims INTEGER NOT NULL,
  chunk_sha256 TEXT,
  embedding vector(768),               -- локальные sentence-transformers (multilingual-e5-base)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(chunk_id, model)
);

CREATE INDEX IF NOT EXISTS idx_tac_embeddings_chunk ON tac.embeddings(chunk_id);
-- Индекс для cosine similarity (опционально; при больших объёмах включить ivfflat/hnsw тюнингом).
CREATE INDEX IF NOT EXISTS idx_tac_embeddings_vec_cos ON tac.embeddings USING ivfflat (embedding vector_cosine_ops);

-- -----------------------------------------------------------------------------
-- tac.entities + tac.chunk_entities (NER)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tac.entities (
  id BIGSERIAL PRIMARY KEY,
  entity_type TEXT NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(entity_type, name)
);

CREATE TABLE IF NOT EXISTS tac.chunk_entities (
  chunk_id BIGINT NOT NULL REFERENCES tac.chunks(id) ON DELETE CASCADE,
  entity_id BIGINT NOT NULL REFERENCES tac.entities(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(chunk_id, entity_id)
);

-- -----------------------------------------------------------------------------
-- op.jobs: асинхронная обработка (ingest/index/enrich)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS op.jobs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT,
  kind TEXT NOT NULL,                 -- ingest_transcript|reindex_document|enrich_document|...
  status TEXT NOT NULL DEFAULT 'queued', -- queued|running|done|error
  payload JSONB NOT NULL DEFAULT '{}',
  result JSONB NOT NULL DEFAULT '{}',
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_op_jobs_status ON op.jobs(status, created_at);

-- -----------------------------------------------------------------------------
-- chat.* (из "запросы по kb.txt"; стартовый каркас)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat.sessions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat.sessions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat.messages (
  id BIGSERIAL PRIMARY KEY,
  session_id BIGINT REFERENCES chat.sessions(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('user','assistant','system')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat.messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS chat.message_citations (
  message_id BIGINT REFERENCES chat.messages(id) ON DELETE CASCADE,
  chunk_id BIGINT REFERENCES tac.chunks(id),
  score DOUBLE PRECISION,
  PRIMARY KEY(message_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS chat.session_memory (
  session_id BIGINT PRIMARY KEY REFERENCES chat.sessions(id),
  summary TEXT,
  updated_at TIMESTAMPTZ DEFAULT now()
);

COMMIT;
