"""Context-assembly policy comparison — the context-engineering artefact.

Runs the in-corpus fixtures through /query under each assembly policy and builds
the **policy × (accuracy, tokens, latency)** table SCOPING_1 §3a-bis calls for:

- accuracy  — groundedness of the answer (agent-evals judge), the metric that
              actually moves with what's in the window. Scored only when
              ANTHROPIC_API_KEY is present; otherwise reported as "—".
- tokens    — mean assembled context tokens (the knapsack cost).
- latency   — p50/p95 of the end-to-end query.

recall@k is included too, but note it's ~constant across policies (same
retrieval); the differentiation lives in tokens/latency/groundedness. That's the
point: assembly is a measured tradeoff, not a free lunch.

Outputs out/assembly_table.{json,md}. Needs a live retrieval-api.
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
_BEARER = os.environ.get("RAG_BEARER_TOKEN", "")
_HEADERS = {"Authorization": f"Bearer {_BEARER}"} if _BEARER else {}
POLICIES = ["top_k_by_fused", "rerank_then_top_k", "rerank_then_compress"]
TOP_KS = [1, 3, 5]


@dataclass
class Fixture:
    query: str
    expected_doc: str
    expected_heading: str
    query_id: str = ""
    category: str = "in_corpus"


@dataclass
class Sample:
    fixture: Fixture
    answer: str
    chunks: list[dict]
    context_tokens: int
    latency_ms: float


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((p / 100) * (len(ordered) - 1)))]


async def _query(client: httpx.AsyncClient, fixture: Fixture, policy: str) -> Sample:
    start = time.perf_counter()
    response = await client.post(
        f"{RETRIEVAL_API_URL}/v1/answer",
        json={
            "query": fixture.query,
            "tenant_id": TENANT_ID,
            "top_k": max(TOP_KS),
            "assembly_policy": policy,
        },
        headers=_HEADERS,
        timeout=120,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    body = response.json()
    return Sample(
        fixture=fixture,
        answer=body.get("answer", ""),
        chunks=body.get("chunks", []),
        context_tokens=body.get("context_tokens", 0),
        latency_ms=latency_ms,
    )


async def _groundedness(samples: list[Sample]) -> float | None:
    """Mean groundedness (0-1) via the agent-evals judge; None without a key."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from agent_evals.judge import JudgeCriterion, run_judge

    criterion = JudgeCriterion(
        name="groundedness",
        prompt=(
            "Judge whether every factual claim in the answer is supported by the "
            "retrieved context shown.\n0 = largely unsupported.\n1 = several claims "
            "unsupported.\n2 = supported, minor unsupported details.\n3 = every claim "
            "grounded in the context."
        ),
        scale="rubric_0_3",
        applies_to_category=("in_corpus",),
    )
    traces = [_make_trace(s) for s in samples]
    judged = await run_judge(records=traces, criteria=[criterion])
    scores = [r.score for r in judged.for_criterion("groundedness")]
    return (sum(scores) / len(scores) / 3.0) if scores else None


def _make_trace(sample: Sample):
    """Minimal TraceRecord the judge can render: question + retrieved context as
    one tool result + the final answer."""
    from agent_evals.trace import ToolCall, TraceRecord

    context = "\n\n".join(
        f"[{c.get('source_doc')} :: {c.get('heading_path')}]\n{c.get('text', '')}"
        for c in sample.chunks
    )
    tool_call = ToolCall(
        turn=1,
        tool="query_knowledge",
        input={"query": sample.fixture.query},
        tool_use_id="tc1",
        result_preview=context,
        result_preview_len=len(context),
        error=None,
    )
    return TraceRecord(
        path=pathlib.Path("synthetic"),
        run_id="assembly",
        query_id=sample.fixture.query_id or sample.fixture.query[:32],
        category=sample.fixture.category,
        expected_tools=("query_knowledge",),
        note="",
        skills_enabled=False,
        question=sample.fixture.query,
        model="",
        prompt_version="",
        available_tools=("query_knowledge",),
        max_turns=1,
        skills_loaded=(),
        system_prompt_chars=0,
        tool_calls=(tool_call,),
        turn_usage=(),
        turns=1,
        tool_call_count=1,
        stop_reason="end_turn",
        final_text=sample.answer,
        final_text_truncated=False,
    )


def _recall_at_k(samples: list[Sample], k: int) -> float:
    hits = sum(
        any(c.get("source_doc") == s.fixture.expected_doc for c in s.chunks[:k])
        for s in samples
    )
    return hits / len(samples)


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
    rows = []
    async with httpx.AsyncClient() as client:
        for policy in POLICIES:
            samples = [await _query(client, f, policy) for f in fixtures]
            latencies = [s.latency_ms for s in samples]
            rows.append(
                {
                    "policy": policy,
                    "groundedness": await _groundedness(samples),
                    "recall_at_k": {k: _recall_at_k(samples, k) for k in TOP_KS},
                    "mean_context_tokens": sum(s.context_tokens for s in samples) / len(samples),
                    "latency_ms": {
                        "p50": _percentile(latencies, 50),
                        "p95": _percentile(latencies, 95),
                    },
                    "n": len(samples),
                }
            )

    (out_dir / "assembly_table.json").write_text(json.dumps(rows, indent=2))
    (out_dir / "assembly_table.md").write_text(_markdown(rows))
    print(json.dumps(rows, indent=2))
    return 0


def _markdown(rows: list[dict]) -> str:
    lines = [
        "# Context-assembly policy comparison",
        "",
        "Policy × (accuracy, tokens, latency) over the in-corpus fixtures.",
        "",
        "| policy | groundedness | recall@5 | mean ctx tokens | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        g = "—" if r["groundedness"] is None else f"{r['groundedness']:.2f}"
        lines.append(
            f"| {r['policy']} | {g} | {r['recall_at_k'][5]:.2f} | "
            f"{r['mean_context_tokens']:.0f} | {r['latency_ms']['p50']:.0f} | "
            f"{r['latency_ms']['p95']:.0f} |"
        )
    lines += [
        "",
        "_Groundedness is the agent-evals judge (0-1); '—' means no judge key was "
        "set. recall@5 is ~constant across policies (same retrieval) — the assembly "
        "tradeoff lives in tokens/latency/groundedness, which is the whole point: "
        "what goes in the window is a measured decision, not a default._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
