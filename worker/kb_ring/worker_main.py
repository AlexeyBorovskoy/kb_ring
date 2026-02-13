import hashlib
import os
import time

from dotenv import load_dotenv
import psycopg
from psycopg.types.json import Jsonb


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
                            """,
                            (doc_id, idx, c, csha, c),
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
