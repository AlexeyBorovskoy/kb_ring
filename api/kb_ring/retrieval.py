from dataclasses import dataclass
from typing import Optional


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
    - Векторный поиск (pgvector) добавим, когда появится пайплайн эмбеддингов.
    """
    q = (query or "").strip()
    if not q:
        return []
    top_k = max(1, min(20, int(top_k)))

    with conn.cursor() as cur:
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
