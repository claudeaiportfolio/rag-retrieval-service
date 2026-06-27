"""Context assembly — turning retrieved candidates into the exact text placed in
the LLM's window, under a fixed token budget.

This is where "context engineering" actually lives (SCOPING_1 §3a-bis). More
context is not monotonically better, the budget is finite, and the right policy
is workload-dependent — so the policy is made **explicit and swappable** and
measured against the same eval (policy × accuracy × tokens × latency) rather than
inherited as a framework default. Three policies:

- ``top_k_by_fused``      — pack RRF-ranked chunks until the budget (no rerank).
- ``rerank_then_top_k``   — pack cross-encoder-reranked chunks until the budget.
- ``rerank_then_compress``— rerank, then extractively compress each chunk (keep
  the sentences most overlapping the query) so more distinct chunks fit.

The compressor is deterministic and model-free (query-term sentence overlap), so
it adds no LLM call and no nondeterminism — assembly stays in the determinate
piece.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import tiktoken

from common.retrieval import Candidate

AssemblyPolicy = Literal["top_k_by_fused", "rerank_then_top_k", "rerank_then_compress"]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\w+")
_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


@dataclass
class AssemblyResult:
    context: str
    chunks_used: int
    tokens: int
    policy: AssemblyPolicy


def _format(chunk: Candidate, text: str | None = None) -> str:
    return f"[{chunk.source_doc} :: {chunk.heading_path}]\n{text if text is not None else chunk.text}"


def _compress(text: str, query: str, max_tokens: int) -> str:
    """Extractive: keep whole sentences, ranked by query-term overlap, until the
    per-chunk token cap — preserving original order so the prose still reads."""
    sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s]
    if len(sentences) <= 1:
        return _truncate(text, max_tokens)
    terms = {w.lower() for w in _WORD.findall(query)}
    scored = [
        (i, sum(1 for w in _WORD.findall(s) if w.lower() in terms))
        for i, s in enumerate(sentences)
    ]
    keep: set[int] = set()
    used = 0
    for idx, _ in sorted(scored, key=lambda pair: pair[1], reverse=True):
        cost = count_tokens(sentences[idx])
        if used + cost > max_tokens:
            continue
        keep.add(idx)
        used += cost
    if not keep:  # even the best single sentence overflows — hard truncate it
        return _truncate(sentences[max(scored, key=lambda p: p[1])[0]], max_tokens)
    return " ".join(sentences[i] for i in sorted(keep))


def _truncate(text: str, max_tokens: int) -> str:
    ids = _encoder.encode(text)
    if len(ids) <= max_tokens:
        return text
    return _encoder.decode(ids[:max_tokens])


def assemble(
    candidates: list[Candidate],
    *,
    policy: AssemblyPolicy,
    token_budget: int,
    query: str,
    compress_per_chunk_tokens: int = 200,
) -> AssemblyResult:
    """Pack candidates into a context string under ``token_budget``.

    Order is whatever ``retrieve`` returned (RRF or reranked — the caller maps
    the policy to the rerank flag). ``rerank_then_compress`` compresses each
    chunk to fit more distinct evidence; the others pack whole chunks greedily.
    """
    parts: list[str] = []
    used = 0
    for chunk in candidates:
        if policy == "rerank_then_compress":
            budget_left = token_budget - used
            if budget_left <= 0:
                break
            text = _compress(chunk.text, query, min(compress_per_chunk_tokens, budget_left))
            formatted = _format(chunk, text)
        else:
            formatted = _format(chunk)
        cost = count_tokens(formatted)
        if used + cost > token_budget:
            break
        parts.append(formatted)
        used += cost
    return AssemblyResult(
        context="\n\n".join(parts),
        chunks_used=len(parts),
        tokens=used,
        policy=policy,
    )
