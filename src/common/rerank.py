"""Cross-encoder reranker client.

A cross-encoder scores (query, passage) *jointly*, so it catches relevance a
bi-encoder (the embedding retriever) can't — at a real latency cost, which is
exactly the tradeoff the rerank ON/OFF eval measures. It's served as a warm pod
(TEI-compatible ``/rerank``), not the LLM.

When ``rerank_enabled`` is off or no ``reranker_url`` is set, ``rerank`` is a
pass-through (preserves input order) so the stack runs without a reranker in
dev/CI; the eval flips ``rerank_enabled`` against a live pod to get the delta.
"""

from __future__ import annotations

import httpx

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from common.config import settings
from common.otel import get_tracer

tracer = get_tracer(__name__)

# Transient reranker faults (pod busy / connection dropped under CPU load) are
# retried; a 4xx like 413 is a contract error and is not retried.
_TRANSIENT = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout)


@retry(
    retry=retry_if_exception_type(_TRANSIENT),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_reranker(query: str, texts: list[str]) -> list[dict]:
    # CPU cross-encoders are slow (queue + inference); give them room before a
    # ReadTimeout. retrieval.retrieve() degrades to fused order if this still fails.
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{settings.reranker_url.rstrip('/')}/rerank",
            json={"query": query, "texts": texts, "truncate": True},
        )
        resp.raise_for_status()
        return resp.json()  # [{"index": i, "score": s}, ...]


async def rerank(query: str, texts: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
    """Return ``[(original_index, score), ...]`` sorted by score desc.

    Pass-through (input order, zero scores) when disabled or given no texts.
    """
    n = len(texts)
    if not settings.rerank_enabled or not settings.reranker_url or n == 0:
        keep = n if top_n is None else min(top_n, n)
        return [(i, 0.0) for i in range(keep)]

    with tracer.start_as_current_span("rerank") as span:
        span.set_attribute("rag.rerank.candidates", n)
        results = await _call_reranker(query, texts)
        ranked = sorted(
            ((int(r["index"]), float(r["score"])) for r in results),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return ranked if top_n is None else ranked[:top_n]
