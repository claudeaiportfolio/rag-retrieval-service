"""Rerank ON/OFF delta — the headline retrieval-quality artefact.

Runs the in-corpus fixtures through /query twice (rerank off, then on),
measuring recall@k and per-request latency for each mode. The committed table
(mode × recall@k, p50, p95) is what justifies the reranker's added p95 cost:
"I added a reranker and measured it improved recall enough to justify its
latency — here's the number." If Δrecall ≈ 0, the reranker isn't earning its
cost on this corpus, and that's the honest finding to report.

Outputs out/rerank_delta.{json,md}. Needs a live retrieval-api with a reranker
pod reachable (settings.reranker_url); the request `rerank` flag overrides the
service default per call.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import time
from dataclasses import dataclass

import httpx

RETRIEVAL_API_URL = os.environ.get(
    "RETRIEVAL_API_URL", "https://retrieve.rag.dev.michaelalinks.com"
)
TENANT_ID = os.environ.get("EVAL_TENANT_ID", "evals")
TOP_KS = [1, 3, 5, 8]


@dataclass
class Fixture:
    query: str
    expected_doc: str
    expected_heading: str
    query_id: str = ""
    category: str = "in_corpus"


async def _query(client: httpx.AsyncClient, fixture: Fixture, rerank: bool) -> tuple[dict, float]:
    start = time.perf_counter()
    response = await client.post(
        f"{RETRIEVAL_API_URL}/query",
        json={
            "query": fixture.query,
            "tenant_id": TENANT_ID,
            "top_k": max(TOP_KS),
            "rerank": rerank,
        },
        timeout=120,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    chunks = response.json().get("chunks", [])
    hit = {k: any(c.get("source_doc") == fixture.expected_doc for c in chunks[:k]) for k in TOP_KS}
    return hit, elapsed_ms


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((p / 100) * (len(ordered) - 1)))
    return ordered[idx]


async def _run_mode(client: httpx.AsyncClient, fixtures: list[Fixture], rerank: bool) -> dict:
    hits: list[dict] = []
    latencies: list[float] = []
    # Sequential so the latency percentiles reflect real per-request cost rather
    # than being skewed by concurrent contention.
    for fixture in fixtures:
        hit, ms = await _query(client, fixture, rerank)
        hits.append(hit)
        latencies.append(ms)
    recall = {k: sum(h[k] for h in hits) / len(hits) for k in TOP_KS}
    return {
        "recall_at_k": recall,
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "mean": sum(latencies) / len(latencies),
        },
        "n": len(fixtures),
    }


async def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    fixtures = [
        Fixture(**json.loads(line))
        for line in (root / "evals/fixtures/queries.jsonl").read_text().splitlines()
        if line.strip()
    ]
    fixtures = [f for f in fixtures if f.category == "in_corpus"]
    if not fixtures:
        print("no in-corpus fixtures", file=sys.stderr)
        return 1

    out_dir = root / "out"
    out_dir.mkdir(exist_ok=True)
    async with httpx.AsyncClient() as client:
        off = await _run_mode(client, fixtures, rerank=False)
        on = await _run_mode(client, fixtures, rerank=True)

    summary = {
        "off": off,
        "on": on,
        "delta": {
            "recall_at_k": {k: on["recall_at_k"][k] - off["recall_at_k"][k] for k in TOP_KS},
            "p95_ms": on["latency_ms"]["p95"] - off["latency_ms"]["p95"],
        },
    }
    (out_dir / "rerank_delta.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "rerank_delta.md").write_text(_markdown(summary))
    print(json.dumps(summary["delta"], indent=2))
    return 0


def _markdown(s: dict) -> str:
    lines = [
        "# Rerank ON/OFF delta",
        "",
        "Recall@k and latency for the in-corpus fixtures, rerank disabled vs enabled.",
        "",
        "| metric | rerank OFF | rerank ON | Δ |",
        "|---|---|---|---|",
    ]
    for k in TOP_KS:
        off, on = s["off"]["recall_at_k"][k], s["on"]["recall_at_k"][k]
        lines.append(f"| recall@{k} | {off:.2f} | {on:.2f} | {on - off:+.2f} |")
    for stat in ("p50", "p95", "mean"):
        off, on = s["off"]["latency_ms"][stat], s["on"]["latency_ms"][stat]
        lines.append(f"| latency {stat} (ms) | {off:.0f} | {on:.0f} | {on - off:+.0f} |")
    lines += [
        "",
        f"_n = {s['off']['n']} in-corpus fixtures. The recall gain is what justifies "
        "the reranker's added p95 cost; if Δrecall ≈ 0 the reranker isn't earning its "
        "latency on this corpus._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
