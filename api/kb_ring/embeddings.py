from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import EMBEDDINGS_BATCH_SIZE, EMBEDDINGS_DIMS, EMBEDDINGS_ENABLED, EMBEDDINGS_MODEL


@dataclass(frozen=True)
class Embedder:
    model_name: str
    dims: int

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_passage(self, text: str) -> list[float]:
        raise NotImplementedError


_EMBEDDER: Optional[Embedder] = None
_EMBEDDER_ERR: Optional[str] = None


def _l2_normalize(v: list[float]) -> list[float]:
    # Normalize for cosine similarity in pgvector.
    import math

    s = 0.0
    for x in v:
        s += float(x) * float(x)
    n = math.sqrt(s) if s > 0.0 else 0.0
    if n <= 0.0:
        return [0.0 for _ in v]
    return [float(x) / n for x in v]


def get_embedder() -> Optional[Embedder]:
    """
    Возвращает локальный эмбеддер (sentence-transformers), если зависимости установлены.
    Если нет — возвращает None и retrieval работает в FTS-only режиме.
    """
    global _EMBEDDER, _EMBEDDER_ERR
    if not EMBEDDINGS_ENABLED:
        return None
    if _EMBEDDER is not None or _EMBEDDER_ERR is not None:
        return _EMBEDDER

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:  # pragma: no cover
        _EMBEDDER_ERR = f"sentence-transformers import failed: {e}"
        return None

    st = SentenceTransformer(EMBEDDINGS_MODEL)

    class _StEmbedder(Embedder):
        def __init__(self):
            super().__init__(model_name=EMBEDDINGS_MODEL, dims=EMBEDDINGS_DIMS)

        def _encode_one(self, text: str) -> list[float]:
            vec = st.encode([text], normalize_embeddings=True, batch_size=EMBEDDINGS_BATCH_SIZE)
            v = [float(x) for x in vec[0].tolist()]
            return _l2_normalize(v)

        def embed_query(self, text: str) -> list[float]:
            # E5 query embeddings: prefix "query: ".
            return self._encode_one("query: " + (text or ""))

        def embed_passage(self, text: str) -> list[float]:
            # E5 passage embeddings: prefix "passage: ".
            return self._encode_one("passage: " + (text or ""))

    emb = _StEmbedder()
    if emb.dims and len(emb.embed_query("ping")) != emb.dims:
        # If the env config is wrong, prefer disabling embeddings rather than crashing API.
        _EMBEDDER_ERR = f"embedding dims mismatch: expected {emb.dims}"
        return None

    _EMBEDDER = emb
    return _EMBEDDER


def pgvector_text(v: list[float]) -> str:
    """
    Формат ввода pgvector: '[0.1,0.2,...]'. Удобно передавать как TEXT параметр.
    """
    return "[" + ",".join(f"{float(x):.8f}" for x in v) + "]"
