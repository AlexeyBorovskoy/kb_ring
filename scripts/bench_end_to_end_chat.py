#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import time

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8099")
    ap.add_argument("--mode", default="rag-tech", choices=["search", "rag", "analysis", "rag-tech"])
    ap.add_argument("--text", default="Дай описание и примеры интерфейсов АСУДД")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--user-id", type=int, default=1)
    args = ap.parse_args()

    times = []
    with httpx.Client(base_url=args.base_url, timeout=120.0) as c:
        # Dev login: set cookie auth_token.
        r = c.post("/api/v1/dev/login", data={"user_id": str(args.user_id)})
        if r.status_code != 200:
            print("dev login failed:", r.text)
            return 2

        r = c.post("/api/v1/chat/sessions", data={"title": "bench"})
        if r.status_code != 200:
            print("create session failed:", r.text)
            return 2
        sid = r.json().get("session_id")
        if not sid:
            print("no session_id")
            return 2

        for _ in range(args.runs):
            t0 = time.time()
            r = c.post(f"/api/v1/chat/sessions/{sid}/message", data={"text": args.text, "mode": args.mode})
            dt = time.time() - t0
            times.append(dt)
            if r.status_code != 200:
                print("request failed:", r.text)
                return 2

    print(f"runs={args.runs} mode={args.mode}")
    print(f"avg_s={statistics.mean(times):.3f} p50_s={statistics.median(times):.3f} max_s={max(times):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

