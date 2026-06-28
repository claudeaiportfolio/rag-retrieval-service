"""Hybrid retrieval: vector (pgvector HNSW) + BM25 (Postgres FTS), fused with
Reciprocal Rank Fusion, optionally cross-encoder reranked, with a freshness
tiebreak.

**Why RRF over weighted-sum.** The two retrievers score on incomparable scales
(cosine similarity vs `ts_rank_cd`), so summing them needs per-corpus
normalisation and weight tuning that doesn't transfer between corpora. RRF fuses
on *rank*, not score — no normalisation, no tuning, a robust default you can
defend without a grid search.

The pipeline is fully determinate: retrieve candidates from each arm → fuse →
(optional) rerank → return top-k. The next step never depends on what the last
step found; that's the piece-1 thesis in code.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from common.config import settings
from common.rerank import rerank

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    id: int
    document_id: str
    source_doc: str
    heading_path: str
    chunk_index: int
    text: str
    created_at: datetime | None
    score: float = 0.0  # final fused (and, if enabled, rerank) score


async def _vector_ids(conn: Any, qvec: str, tenant: str, k: int) -> list[int]:
    rows = await conn.fetch(
        """
        SELECT id FROM chunks
        WHERE tenant_id = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        qvec,
        tenant,
        k,
    )
    return [r["id"] for r in rows]


async def _bm25_ids(conn: Any, query_text: str, tenant: str, k: int) -> list[int]:
    # websearch_to_tsquery accepts user-style queries ("foo bar", quotes, OR)
    # safely — no tsquery-injection surface. ts_rank_cd rewards term density +
    # proximity (the BM25-ish signal Postgres FTS gives natively).
    rows = await conn.fetch(
        """
        SELECT id
        FROM chunks
        WHERE tenant_id = $2
          AND tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', $1)) DESC
        LIMIT $3
        """,
        query_text,
        tenant,
        k,
    )
    return [r["id"] for r in rows]


async def _fetch_rows(conn: Any, ids: list[int], tenant: str) -> dict[int, Any]:
    rows = await conn.fetch(
        """
        SELECT id, document_id, source_doc, heading_path, chunk_index, text, created_at
        FROM chunks
        WHERE id = ANY($1::bigint[]) AND tenant_id = $2
        """,
        ids,
        tenant,
    )
    return {r["id"]: r for r in rows}


def rrf_fuse(rankings: list[list[int]], rrf_k: int) -> dict[int, float]:
    """Reciprocal Rank Fusion. ``score(d) = Σ 1/(rrf_k + rank_d)`` over the lists
    that contain ``d`` (rank 0-based). Pure + deterministic — unit-tested."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return scores


def _freshness_boost(created_at: datetime | None, half_life_days: float, now: datetime) -> float:
    """Tiny additive boost decaying by age, capped below one RRF rank-step so it
    only breaks near-ties (never reorders a clearly-better chunk). 0 when off."""
    if half_life_days <= 0 or created_at is None:
        return 0.0
    age_days = (now - created_at).total_seconds() / 86400.0
    return (0.5 / settings.rrf_k) * math.exp(-age_days * math.log(2) / half_life_days)


async def retrieve(
    conn: Any,
    *,
    query: str,
    qvec: str,
    tenant: str,
    top_k: int,
    hybrid: bool | None = None,
    rerank_on: bool | None = None,
) -> list[Candidate]:
    """Run the hybrid pipeline and return the final top-k candidates."""
    hybrid = settings.hybrid_enabled if hybrid is None else hybrid
    rerank_on = settings.rerank_enabled if rerank_on is None else rerank_on
    ck = settings.candidate_k

    rankings = [await _vector_ids(conn, qvec, tenant, ck)]
    if hybrid:
        rankings.append(await _bm25_ids(conn, query, tenant, ck))

    fused = rrf_fuse(rankings, settings.rrf_k)
    if not fused:
        return []

    candidate_ids = sorted(fused, key=lambda i: fused[i], reverse=True)[:ck]
    rows = await _fetch_rows(conn, candidate_ids, tenant)
    now = datetime.now(UTC)

    candidates: list[Candidate] = []
    for cid in candidate_ids:
        r = rows.get(cid)
        if r is None:
            continue
        score = fused[cid] + _freshness_boost(
            r["created_at"], settings.freshness_half_life_days, now
        )
        candidates.append(
            Candidate(
                id=cid,
                document_id=r["document_id"],
                source_doc=r["source_doc"],
                heading_path=r["heading_path"],
                chunk_index=r["chunk_index"],
                text=r["text"],
                created_at=r["created_at"],
                score=score,
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)

    if rerank_on and candidates:
        try:
            order = await rerank(query, [c.text for c in candidates], top_n=top_k)
            reranked: list[Candidate] = []
            for orig_idx, rscore in order:
                c = candidates[orig_idx]
                c.score = rscore
                reranked.append(c)
            return reranked[:top_k]
        except Exception:
            # A reranker blip must not fail the query — degrade to the fused
            # (still hybrid-ranked) order and log so the dip is observable.
            logger.warning("event=rerank_unavailable action=degrade_to_fused")

    return candidates[:top_k]
