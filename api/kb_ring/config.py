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

# Local embeddings (обязательно по ТЗ, OpenAI embedding не используем для retrieval).
# Если зависимости не установлены (sentence-transformers/torch), сервис продолжит работать в режиме FTS-only.
EMBEDDINGS_ENABLED = env("EMBEDDINGS_ENABLED", "1").lower() in ("1", "true", "yes")
EMBEDDINGS_MODEL = env("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDINGS_DIMS = int(env("EMBEDDINGS_DIMS", "384") or "384")
EMBEDDINGS_BATCH_SIZE = int(env("EMBEDDINGS_BATCH_SIZE", "32") or "32")
