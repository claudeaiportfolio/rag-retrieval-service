"""Pure-logic tests for context assembly (no DB / no LLM)."""

from common.assembly import _compress, assemble
from common.retrieval import Candidate


def _cand(text: str, doc: str = "d", heading: str = "h") -> Candidate:
    return Candidate(
        id=1,
        document_id=doc,
        source_doc=doc,
        heading_path=heading,
        chunk_index=0,
        text=text,
        created_at=None,
        score=1.0,
    )


def test_assemble_respects_token_budget():
    cands = [_cand("word " * 100) for _ in range(10)]
    res = assemble(cands, policy="rerank_then_top_k", token_budget=200, query="word")
    assert res.tokens <= 200
    assert res.chunks_used < 10  # budget stops packing short of all chunks


def test_compress_fits_more_distinct_chunks_than_whole():
    long = " ".join(f"Sentence {i} about alpha beta gamma." for i in range(20))
    cands = [_cand(long, doc=f"d{i}") for i in range(5)]
    whole = assemble(cands, policy="rerank_then_top_k", token_budget=300, query="alpha")
    compressed = assemble(
        cands,
        policy="rerank_then_compress",
        token_budget=300,
        query="alpha",
        compress_per_chunk_tokens=40,
    )
    assert compressed.chunks_used >= whole.chunks_used
    assert compressed.tokens <= 300


def test_compress_keeps_query_relevant_sentences():
    text = "Totally unrelated filler. The alpha clause governs lending. More filler here."
    out = _compress(text, "alpha clause lending", max_tokens=12)
    assert "alpha" in out.lower()


def test_policy_is_recorded():
    res = assemble([_cand("x")], policy="top_k_by_fused", token_budget=100, query="x")
    assert res.policy == "top_k_by_fused"
    assert res.chunks_used == 1
