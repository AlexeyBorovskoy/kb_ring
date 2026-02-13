#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path
import sys


def _import_api():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "api"))
    from kb_ring.db import db_conn  # type: ignore
    from kb_ring.retrieval import hybrid_retrieve  # type: ignore
    from kb_ring.rerank_bge import Candidate, rerank  # type: ignore

    return db_conn, hybrid_retrieve, Candidate, rerank


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True, help="Path to txt file with one question per line")
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--top-m", type=int, default=15)
    args = ap.parse_args()

    db_conn, hybrid_retrieve, Candidate, rerank = _import_api()

    qs = [ln.strip() for ln in Path(args.questions).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not qs:
        print("no questions")
        return 2

    times = []
    with db_conn() as conn:
        for q in qs:
            base = hybrid_retrieve(conn, args.user_id, q, top_k=args.top_n)
            cand = [
                Candidate(
                    chunk_id=r.chunk_id,
                    doc_id=r.doc_id,
                    title=r.title,
                    uri=r.uri,
                    content=r.content or "",
                    base_score=float(r.score or 0.0),
                )
                for r in base
            ]
            t0 = time.time()
            _ = rerank(q, cand, top_m=args.top_m)
            times.append(time.time() - t0)

    print(f"questions={len(qs)} top_n={args.top_n} top_m={args.top_m}")
    print(f"avg_s={statistics.mean(times):.3f} p50_s={statistics.median(times):.3f} max_s={max(times):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

