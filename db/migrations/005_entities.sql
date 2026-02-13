-- KB-RING миграция 005: хранение NER результатов (entities + связи chunk->entity).

BEGIN;

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

COMMIT;

