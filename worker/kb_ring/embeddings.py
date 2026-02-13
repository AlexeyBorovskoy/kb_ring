from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import os


def _env_bool(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or default).lower() in ("1", "true", "yes")


def _env_int(name: str, default: str) -> int:
    v = os.environ.get(name)
    return int((default if v is None else v) or default)


EMBEDDINGS_ENABLED = _env_bool("EMBEDDINGS_ENABLED", "1")
EMBEDDINGS_MODEL = os.environ.get("EMBEDDINGS_MODEL", "sentence-transformers/multilingual-e5-base")
EMBEDDINGS_DIMS = _env_int("EMBEDDINGS_DIMS", "768")
EMBEDDINGS_BATCH_SIZE = _env_int("EMBEDDINGS_BATCH_SIZE", "32")


@dataclass(frozen=True)
class Embedder:
    model_name: str
    dims: int

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


_EMBEDDER: Optional[Embedder] = None
_EMBEDDER_ERR: Optional[str] = None


def get_embedder() -> Optional[Embedder]:
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

        def embed_many(self, texts: list[str]) -> list[list[float]]:
            # E5 passage embeddings: prefix "passage: ".
            batch = ["passage: " + (t or "") for t in texts]
            vecs = st.encode(batch, normalize_embeddings=True, batch_size=EMBEDDINGS_BATCH_SIZE)
            return [[float(x) for x in v.tolist()] for v in vecs]

    emb = _StEmbedder()
    try:
        if emb.dims and len(emb.embed_many(["ping"])[0]) != emb.dims:
            _EMBEDDER_ERR = "embedding dims mismatch"
            return None
    except Exception:
        _EMBEDDER_ERR = "embedding init failed"
        return None

    _EMBEDDER = emb
    return _EMBEDDER


def pgvector_text(v: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in v) + "]"
