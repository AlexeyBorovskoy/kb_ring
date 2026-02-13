-- KB-RING миграция 002: chat-сессии/сообщения + citations.
-- Основано на: /home/alexey/shared_vm/запросы по kb.txt
--
-- Примечание: добавляем `user_id`, чтобы модель авторизации совпадала с TG (JWT `sub=user_id`).

BEGIN;

CREATE SCHEMA IF NOT EXISTS chat;

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
