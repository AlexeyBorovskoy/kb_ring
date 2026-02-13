-- KB-RING миграция 003: добавить каноническую `uri` в tac.documents для citations.
BEGIN;

ALTER TABLE tac.documents
  ADD COLUMN IF NOT EXISTS uri TEXT;

CREATE INDEX IF NOT EXISTS idx_tac_documents_uri ON tac.documents(uri);

COMMIT;
