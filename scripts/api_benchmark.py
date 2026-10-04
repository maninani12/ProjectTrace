"""Bounded concurrent local API smoke load. Does not call external providers."""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


def summarize(values):
    durations = sorted(v["ms"] for v in values)
    return {
        "requests": len(values),
        "errors": sum(v["status"] != 200 for v in values),
        "p50_ms": round(statistics.median(durations), 2),
        "p95_ms": round(durations[int(len(durations) * 0.95)], 2),
        "p99_ms": round(durations[-1], 2),
    }


if __name__ == "__main__":
    with httpx.Client(
        base_url="http://127.0.0.1:8011", headers={"Origin": "http://127.0.0.1:5181"}, timeout=20
    ) as client:
        session = client.post("/api/auth/demo", json={})
        session.raise_for_status()
        cookies = dict(client.cookies)
        headers = {"Origin": "http://127.0.0.1:5181", "X-CSRF-Token": session.json()["csrf"]}

    def request(index):
        with httpx.Client(base_url="http://127.0.0.1:8011", cookies=cookies, headers=headers, timeout=20) as client:
            start = time.perf_counter()
            response = (
                client.get("/api/workspace")
                if index % 2 == 0
                else client.post(
                    "/api/ask", json={"question": "How is authentication implemented?", "repository_id": "identity"}
                )
            )
            return {
                "route": "workspace" if index % 2 == 0 else "ask",
                "ms": (time.perf_counter() - start) * 1000,
                "status": response.status_code,
            }

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(request, range(40)))
    elapsed = time.perf_counter() - start
    print(
        json.dumps(
            {
                "environment": "Local Windows; 4 concurrent clients, SQLite, seeded fixture data; not a capacity claim",
                "workspace": summarize([r for r in results if r["route"] == "workspace"]),
                "ask": summarize([r for r in results if r["route"] == "ask"]),
                "elapsed_seconds": round(elapsed, 2),
                "client_throughput_rps": round(40 / elapsed, 2),
            },
            indent=2,
        )
    )
