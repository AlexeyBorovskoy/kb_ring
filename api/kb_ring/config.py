import os


def env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return default if v is None else v


DATABASE_URL = env("DATABASE_URL", "postgresql://kb_ring:kb_ring_local@127.0.0.1:15432/kb_ring")

# Авторизация (выравниваем под TG)
JWT_SECRET = env("JWT_SECRET", "")
AUTH_COOKIE_NAME = env("AUTH_COOKIE_NAME", "auth_token")
AUTH_COOKIE_DOMAIN = env("AUTH_COOKIE_DOMAIN", "")
AUTH_COOKIE_SECURE = env("AUTH_COOKIE_SECURE", "1").lower() in ("1", "true", "yes")

# OpenAI (этап 1, опционально)
OPENAI_API_KEY = env("OPENAI_API_KEY", "")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = env("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = env("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Local embeddings (обязательно по ТЗ; LLM embeddings не используем для retrieval).
# Если зависимости не установлены (sentence-transformers/torch), сервис продолжит работать в режиме FTS-only.
EMBEDDINGS_ENABLED = env("EMBEDDINGS_ENABLED", "1").lower() in ("1", "true", "yes")
# E5 требует разные префиксы для query/passage. См. embeddings.py.
EMBEDDINGS_MODEL = env("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-base")
EMBEDDINGS_DIMS = int(env("EMBEDDINGS_DIMS", "768") or "768")
EMBEDDINGS_BATCH_SIZE = int(env("EMBEDDINGS_BATCH_SIZE", "32") or "32")

# Reranker (локально, CPU): BGE cross-encoder.
RERANK_ENABLED = env("RERANK_ENABLED", "1").lower() in ("1", "true", "yes")
RERANK_MODEL = env("RERANK_MODEL", "BAAI/bge-reranker-base")
RERANK_TOP_N = int(env("RERANK_TOP_N", "50") or "50")
RERANK_TOP_M = int(env("RERANK_TOP_M", "15") or "15")
RERANK_MAX_PASSAGE_CHARS = int(env("RERANK_MAX_PASSAGE_CHARS", "1400") or "1400")

# Ollama (опционально): локальные черновики. Используем только как fallback (например для rag-tech без OPENAI_API_KEY).
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = env("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
