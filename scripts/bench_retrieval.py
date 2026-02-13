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

    return db_conn, hybrid_retrieve


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True, help="Path to txt file with one question per line")
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--top-n", type=int, default=50)
    args = ap.parse_args()

    db_conn, hybrid_retrieve = _import_api()

    qs = [ln.strip() for ln in Path(args.questions).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not qs:
        print("no questions")
        return 2

    times = []
    counts = []
    with db_conn() as conn:
        for q in qs:
            t0 = time.time()
            items = hybrid_retrieve(conn, args.user_id, q, top_k=args.top_n)
            dt = time.time() - t0
            times.append(dt)
            counts.append(len(items))

    print(f"questions={len(qs)} top_n={args.top_n}")
    print(f"avg_s={statistics.mean(times):.3f} p50_s={statistics.median(times):.3f} max_s={max(times):.3f}")
    print(f"avg_hits={statistics.mean(counts):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

