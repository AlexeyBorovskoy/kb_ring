import hashlib
import os
import time

from dotenv import load_dotenv
import psycopg
from psycopg.types.json import Jsonb

from .embeddings import get_embedder, pgvector_text

load_dotenv(override=False)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    # Простой стартовый чанклинг. Позже заменим на токен-ориентированный.
    text = (text or "").strip()
    if not text:
        return []
    out = []
    i = 0
    while i < len(text):
        out.append(text[i : i + max_chars])
        i += max_chars
    return out


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL не задан")

    while True:
        did_work = False
        with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, payload
                    FROM op.jobs
                    WHERE status = 'queued'
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                row = cur.fetchone()
                if not row:
                    conn.commit()
                else:
                    did_work = True
                    job_id, user_id, payload = row
                    cur.execute("UPDATE op.jobs SET status='running', started_at=now() WHERE id=%s", (job_id,))
                    conn.commit()

        if not did_work:
            time.sleep(2.0)
            continue

        # Обрабатываем задачу уже вне транзакции блокировки.
        try:
            with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT payload FROM op.jobs WHERE id=%s", (job_id,))
                    payload = cur.fetchone()[0]
                    doc_id = int((payload or {}).get("document_id") or 0)
                    if doc_id <= 0:
                        raise RuntimeError("в payload задачи нет document_id")

                    cur.execute(
                        "SELECT user_id, body_text FROM tac.documents WHERE id=%s",
                        (doc_id,),
                    )
                    drow = cur.fetchone()
                    if not drow:
                        raise RuntimeError(f"документ не найден: {doc_id}")
                    doc_user_id, body_text = drow
                    if doc_user_id is None:
                        doc_user_id = user_id

                    chunks = _chunk_text(body_text)
                    chunk_rows: list[tuple[int, str, str]] = []  # (chunk_id, chunk_sha256, chunk_text)
                    for idx, c in enumerate(chunks):
                        csha = _sha(c)
                        cur.execute(
                            """
                            INSERT INTO tac.chunks (document_id, chunk_index, chunk_text, chunk_sha256, tsv)
                            VALUES (%s, %s, %s, %s, to_tsvector('simple', %s))
                            ON CONFLICT (document_id, chunk_index)
                            DO UPDATE SET chunk_text=excluded.chunk_text,
                                          chunk_sha256=excluded.chunk_sha256,
                                          tsv=excluded.tsv
                            RETURNING id
                            """,
                            (doc_id, idx, c, csha, c),
                        )
                        chunk_id = int(cur.fetchone()[0])
                        chunk_rows.append((chunk_id, csha, c))

                    # Local embeddings (sentence-transformers): compute only for changed/missing chunks.
                    embedder = get_embedder()
                    # DB schema currently fixed to vector(384). If config/model differs, skip embeddings.
                    if embedder is not None and int(getattr(embedder, "dims", 0) or 0) == 384 and chunk_rows:
                        chunk_ids = [r[0] for r in chunk_rows]
                        cur.execute(
                            "SELECT chunk_id, chunk_sha256 FROM tac.embeddings WHERE model=%s AND chunk_id = ANY(%s)",
                            (embedder.model_name, chunk_ids),
                        )
                        existing = {int(r[0]): (r[1] or "") for r in cur.fetchall()}

                        to_embed: list[tuple[int, str, str]] = []
                        for chunk_id, csha, ctext in chunk_rows:
                            if existing.get(chunk_id) != csha:
                                to_embed.append((chunk_id, csha, ctext))

                        if to_embed:
                            texts = [r[2] for r in to_embed]
                            vecs = embedder.embed_many(texts)
                            for (chunk_id, csha, _), v in zip(to_embed, vecs):
                                cur.execute(
                                    """
                                    INSERT INTO tac.embeddings (chunk_id, model, dims, chunk_sha256, embedding)
                                    VALUES (%s, %s, %s, %s, (%s)::vector(384))
                                    ON CONFLICT (chunk_id, model)
                                    DO UPDATE SET dims=excluded.dims,
                                                  chunk_sha256=excluded.chunk_sha256,
                                                  embedding=excluded.embedding,
                                                  created_at=now()
                                    """,
                                    (chunk_id, embedder.model_name, embedder.dims, csha, pgvector_text(v)),
                                )

                    cur.execute(
                        "UPDATE op.jobs SET status='done', finished_at=now(), result=%s WHERE id=%s",
                        (Jsonb({"chunks": len(chunks)}), job_id),
                    )
                conn.commit()
        except Exception as e:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE op.jobs SET status='error', finished_at=now(), error=%s WHERE id=%s",
                        (str(e), job_id),
                    )


if __name__ == "__main__":
    main()
