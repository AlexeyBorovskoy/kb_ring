-- KB-RING миграция 004: локальные embeddings (sentence-transformers) + pgvector.
-- Важно: таблица tac.embeddings была каркасом. Миграция делает её пригодной для локальной модели 384 dims.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS tac.embeddings;

CREATE TABLE tac.embeddings (
  id BIGSERIAL PRIMARY KEY,
  chunk_id BIGINT NOT NULL REFERENCES tac.chunks(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  dims INTEGER NOT NULL,
  chunk_sha256 TEXT,
  embedding vector(384) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(chunk_id, model)
);

CREATE INDEX IF NOT EXISTS idx_tac_embeddings_chunk ON tac.embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_tac_embeddings_vec_cos ON tac.embeddings USING ivfflat (embedding vector_cosine_ops);

COMMIT;

