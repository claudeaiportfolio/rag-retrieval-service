"""Load test against /v1/answer → per-stage p50/p95/p99 + a committed plot.

Fires `--requests` queries at `--concurrency`, reading the per-stage timings the
endpoint returns (embed / retrieve / assemble / generate) plus end-to-end
latency. Aggregates percentiles and writes out/latency.{json,png}.

The PNG is the "where does the latency go" artefact: it *attributes* the
rerank cost (inside retrieve) so the reranker's p95 is defensible, not
hand-waved. Set RAG_BEARER_TOKEN for an authed (edge) endpoint.

    uv run python scripts/loadtest.py --requests 200 --concurrency 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import time

import httpx
from common.http import transient_retry

RETRIEVAL_API_URL = os.environ.get(
    "RETRIEVAL_API_URL", "https://retrieve.rag.dev.michaelalinks.com"
)
TENANT_ID = os.environ.get("EVAL_TENANT_ID", "evals")
STAGES = ["embed", "retrieve", "assemble", "generate"]
PERCENTILES = [("p50", 50), ("p95", 95), ("p99", 99)]


def _load_queries(root: pathlib.Path) -> list[str]:
    path = root / "evals/fixtures/queries.jsonl"
    if not path.exists():
        return ["What is the policy?"]
    queries = [json.loads(line)["query"] for line in path.read_text().splitlines() if line.strip()]
    return queries or ["What is the policy?"]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((p / 100) * (len(ordered) - 1)))]


@transient_retry()
async def _answer(client: httpx.AsyncClient, query: str, headers: dict) -> dict:
    response = await client.post(
        f"{RETRIEVAL_API_URL}/v1/answer",
        json={"query": query, "tenant_id": TENANT_ID, "top_k": 8},
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


async def _worker(
    client: httpx.AsyncClient,
    queries: list[str],
    offset: int,
    count: int,
    results: list[dict],
    token: str,
) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    for i in range(count):
        query = queries[(offset + i) % len(queries)]
        start = time.perf_counter()
        try:
            body = await _answer(client, query, headers)
            total = (time.perf_counter() - start) * 1000
            results.append({"total": total, "timings": body.get("timings_ms", {})})
        except Exception as exc:  # noqa: BLE001 — record, don't abort the run
            results.append({"error": str(exc)[:120]})


async def run(requests: int, concurrency: int, token: str) -> dict:
    root = pathlib.Path(__file__).resolve().parents[1]
    queries = _load_queries(root)
    per_worker = max(1, requests // concurrency)
    results: list[dict] = []
    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            *(
                _worker(client, queries, w * per_worker, per_worker, results, token)
                for w in range(concurrency)
            )
        )

    ok = [r for r in results if "error" not in r]
    summary = {
        "requests": len(results),
        "errors": len(results) - len(ok),
        "concurrency": concurrency,
        "total_ms": {name: _percentile([r["total"] for r in ok], p) for name, p in PERCENTILES},
        "stage_ms": {
            stage: {
                name: _percentile([r["timings"].get(stage, 0.0) for r in ok], p)
                for name, p in PERCENTILES
            }
            for stage in STAGES
        },
    }
    out_dir = root / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "latency.json").write_text(json.dumps(summary, indent=2))
    _plot(summary, out_dir / "latency.png")
    print(json.dumps(summary, indent=2))
    return summary


def _plot(summary: dict, path: pathlib.Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs = [name for name, _ in PERCENTILES]
    fig, ax = plt.subplots(figsize=(8, 5))
    bottom = [0.0, 0.0, 0.0]
    for stage in STAGES:
        vals = [summary["stage_ms"][stage][name] for name in xs]
        ax.bar(xs, vals, bottom=bottom, label=stage)
        bottom = [b + v for b, v in zip(bottom, vals, strict=True)]
    ax.set_ylabel("latency (ms)")
    ax.set_title(
        f"Per-stage latency under load (n={summary['requests']}, "
        f"c={summary['concurrency']}, errors={summary['errors']})"
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(run(args.requests, args.concurrency, os.environ.get("RAG_BEARER_TOKEN", "")))


if __name__ == "__main__":
    main()
