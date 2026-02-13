from dataclasses import dataclass
from typing import Optional

from .embeddings import get_embedder, pgvector_text

@dataclass
class RetrievedChunk:
    chunk_id: int
    doc_id: int
    title: Optional[str]
    uri: Optional[str]
    content: str
    score: float


def hybrid_retrieve(conn, user_id: int, query: str, top_k: int = 15) -> list[RetrievedChunk]:
    """
    Этап 1:
    - FTS поиск по `tac.chunks.tsv`
    - Векторный поиск (pgvector) по `tac.embeddings` (локальные sentence-transformers).
    """
    q = (query or "").strip()
    if not q:
        return []
    top_k = max(1, min(20, int(top_k)))

    embedder = get_embedder()
    qvec_txt: Optional[str] = None
    model: Optional[str] = None
    if embedder is not None:
        # DB schema currently fixed to vector(384). If config/model differs, fall back to FTS-only.
        if int(getattr(embedder, "dims", 0) or 0) != 384:
            embedder = None
        else:
            try:
                qvec = embedder.embed_one(q)
                qvec_txt = pgvector_text(qvec)
                model = embedder.model_name
            except Exception:
                # FTS-only fallback on any embedder failure.
                qvec_txt = None
                model = None

    with conn.cursor() as cur:
        if qvec_txt and model:
            # Hybrid:
            # - FTS score: ts_rank
            # - Vector score: cosine similarity = 1 - cosine_distance (pgvector <=>)
            # Combined score is a weighted sum; weights are pragmatic defaults for MVP.
            cur.execute(
                """
                WITH
                  fts AS (
                    SELECT
                      c.id AS chunk_id,
                      ts_rank(c.tsv, plainto_tsquery('simple', %(q)s)) AS s_fts
                    FROM tac.chunks c
                    JOIN tac.documents d ON d.id = c.document_id
                    WHERE d.user_id = %(user_id)s
                      AND c.tsv @@ plainto_tsquery('simple', %(q)s)
                    ORDER BY s_fts DESC
                    LIMIT 200
                  ),
                  vec AS (
                    SELECT
                      e.chunk_id AS chunk_id,
                      (1.0 - (e.embedding <=> (%(qvec)s)::vector(384))) AS s_vec
                    FROM tac.embeddings e
                    JOIN tac.chunks c ON c.id = e.chunk_id
                    JOIN tac.documents d ON d.id = c.document_id
                    WHERE d.user_id = %(user_id)s
                      AND e.model = %(model)s
                    ORDER BY e.embedding <=> (%(qvec)s)::vector(384)
                    LIMIT 200
                  ),
                  comb AS (
                    SELECT
                      COALESCE(fts.chunk_id, vec.chunk_id) AS chunk_id,
                      COALESCE(fts.s_fts, 0.0) AS s_fts,
                      COALESCE(vec.s_vec, 0.0) AS s_vec,
                      (0.55 * COALESCE(fts.s_fts, 0.0) + 0.45 * COALESCE(vec.s_vec, 0.0)) AS score
                    FROM fts
                    FULL OUTER JOIN vec ON vec.chunk_id = fts.chunk_id
                  )
                SELECT
                  c.id AS chunk_id,
                  d.id AS doc_id,
                  d.title AS title,
                  d.uri AS uri,
                  c.chunk_text AS content,
                  comb.score AS score
                FROM comb
                JOIN tac.chunks c ON c.id = comb.chunk_id
                JOIN tac.documents d ON d.id = c.document_id
                WHERE d.user_id = %(user_id)s
                ORDER BY comb.score DESC
                LIMIT %(top_k)s
                """,
                {"q": q, "user_id": user_id, "top_k": top_k, "qvec": qvec_txt, "model": model},
            )
        else:
            cur.execute(
                """
                SELECT
                  c.id AS chunk_id,
                  d.id AS doc_id,
                  d.title AS title,
                  d.uri AS uri,
                  c.chunk_text AS content,
                  ts_rank(c.tsv, plainto_tsquery('simple', %s)) AS score
                FROM tac.chunks c
                JOIN tac.documents d ON d.id = c.document_id
                WHERE d.user_id = %s
                  AND c.tsv @@ plainto_tsquery('simple', %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (q, user_id, q, top_k),
            )
        rows = cur.fetchall()

    out: list[RetrievedChunk] = []
    for r in rows:
        out.append(
            RetrievedChunk(
                chunk_id=int(r[0]),
                doc_id=int(r[1]),
                title=r[2],
                uri=r[3],
                content=r[4] or "",
                score=float(r[5] or 0.0),
            )
        )
    return out
