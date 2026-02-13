from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import RERANK_ENABLED, RERANK_MAX_PASSAGE_CHARS, RERANK_MODEL


@dataclass
class Candidate:
    chunk_id: int
    doc_id: int
    title: Optional[str]
    uri: Optional[str]
    content: str
    base_score: float
    rerank_score: Optional[float] = None


_RERANKER = None
_RERANKER_ERR: Optional[str] = None


def _get_reranker():
    global _RERANKER, _RERANKER_ERR
    if not RERANK_ENABLED:
        return None
    if _RERANKER is not None or _RERANKER_ERR is not None:
        return _RERANKER

    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception as e:  # pragma: no cover
        _RERANKER_ERR = f"cross-encoder import failed: {e}"
        return None

    try:
        _RERANKER = CrossEncoder(RERANK_MODEL)
        return _RERANKER
    except Exception as e:  # pragma: no cover
        _RERANKER_ERR = f"cross-encoder init failed: {e}"
        return None


def rerank(query: str, candidates: list[Candidate], top_m: int) -> list[Candidate]:
    """
    CPU rerank top-N candidates using BGE cross-encoder.
    Returns candidates sorted by rerank_score desc (keeps only top_m).
    """
    q = (query or "").strip()
    if not q or not candidates or top_m <= 0:
        return candidates[: max(0, top_m)]

    r = _get_reranker()
    if r is None:
        # fallback: keep base_score ordering
        out = sorted(candidates, key=lambda c: float(c.base_score), reverse=True)
        return out[:top_m]

    pairs = []
    trimmed: list[Candidate] = []
    for c in candidates:
        passage = (c.content or "").strip()
        if len(passage) > RERANK_MAX_PASSAGE_CHARS:
            passage = passage[:RERANK_MAX_PASSAGE_CHARS]
        trimmed.append(c)
        pairs.append((q, passage))

    try:
        scores = r.predict(pairs)
    except Exception:
        out = sorted(candidates, key=lambda c: float(c.base_score), reverse=True)
        return out[:top_m]

    out = []
    for c, s in zip(trimmed, scores):
        c.rerank_score = float(s)
        out.append(c)

    out.sort(key=lambda c: float(c.rerank_score or 0.0), reverse=True)
    return out[:top_m]

