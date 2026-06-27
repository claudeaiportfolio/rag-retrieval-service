"""Layer 1 deterministic recall@k against the live retrieval-api.

For each query in fixtures/queries.jsonl, hit the retrieval endpoint and
check whether the expected document (and ideally heading) appears in the
top-k chunks. Outputs out/layer1.{json,md}.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
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


@dataclass
class Result:
    fixture: Fixture
    chunks: list[dict]
    hit_at: dict[int, bool]
    heading_hit_at: dict[int, bool]


async def score_one(client: httpx.AsyncClient, fixture: Fixture) -> Result:
    response = await client.post(
        f"{RETRIEVAL_API_URL}/query",
        json={"query": fixture.query, "tenant_id": TENANT_ID, "top_k": max(TOP_KS)},
        timeout=60,
    )
    response.raise_for_status()
    chunks = response.json().get("chunks", [])
    hit = {k: False for k in TOP_KS}
    heading_hit = {k: False for k in TOP_KS}
    for k in TOP_KS:
        topk = chunks[:k]
        for chunk in topk:
            if chunk.get("source_doc") == fixture.expected_doc:
                hit[k] = True
                if fixture.expected_heading.lower() in (chunk.get("heading_path") or "").lower():
                    heading_hit[k] = True
    return Result(fixture=fixture, chunks=chunks, hit_at=hit, heading_hit_at=heading_hit)


async def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    fixtures_path = root / "evals/fixtures/queries.jsonl"
    out_dir = root / "out"
    out_dir.mkdir(exist_ok=True)

    # recall@k is only meaningful for answerable (in-corpus) questions; the
    # out-of-corpus fixtures exist to exercise refusal in the Layer-2 judge.
    fixtures = [
        Fixture(**json.loads(line)) for line in fixtures_path.read_text().splitlines() if line.strip()
    ]
    fixtures = [f for f in fixtures if f.category == "in_corpus"]
    if not fixtures:
        print("no fixtures", file=sys.stderr)
        return 1

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(score_one(client, f) for f in fixtures))

    recall_doc: dict[int, float] = {}
    recall_heading: dict[int, float] = {}
    for k in TOP_KS:
        recall_doc[k] = sum(r.hit_at[k] for r in results) / len(results)
        recall_heading[k] = sum(r.heading_hit_at[k] for r in results) / len(results)

    summary = {
        "fixture_count": len(results),
        "recall_doc_at_k": recall_doc,
        "recall_heading_at_k": recall_heading,
        "results": [
            {
                "query": r.fixture.query,
                "expected_doc": r.fixture.expected_doc,
                "expected_heading": r.fixture.expected_heading,
                "hit_at": r.hit_at,
                "heading_hit_at": r.heading_hit_at,
                "top_chunks": [
                    {
                        "source_doc": c.get("source_doc"),
                        "heading_path": c.get("heading_path"),
                        "score": c.get("score"),
                    }
                    for c in r.chunks[:3]
                ],
            }
            for r in results
        ],
    }

    (out_dir / "layer1.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "layer1.md").write_text(_markdown(summary))
    print(json.dumps({"recall_doc": recall_doc, "recall_heading": recall_heading}, indent=2))
    return 0


def _markdown(summary: dict) -> str:
    lines = ["# Layer 1 recall@k", "", f"Fixtures: {summary['fixture_count']}", "", "| k | recall (doc) | recall (heading) |", "|---|---|---|"]
    for k in TOP_KS:
        lines.append(
            f"| {k} | {summary['recall_doc_at_k'][k]:.2f} | {summary['recall_heading_at_k'][k]:.2f} |"
        )
    lines.append("\n## Misses\n")
    for r in summary["results"]:
        if not r["hit_at"][TOP_KS[-1]]:
            lines.append(f"- **{r['query']}** — expected `{r['expected_doc']}` / `{r['expected_heading']}`")
            for c in r["top_chunks"]:
                lines.append(f"  - top: `{c['source_doc']}` / `{c['heading_path']}` (score {c['score']:.3f})")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
