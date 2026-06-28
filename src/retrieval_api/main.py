"""retrieval-api: query → embed → vector search → LLM answer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException

from common.assembly import assemble
from common.auth import require_scope
from common.config import load_secrets, settings
from common.db import create_pool
from common.embeddings import embed_batch
from common.llm import answer
from common.models import (
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
    SearchRequest,
    SearchResponse,
)
from common.retrieval import Candidate, retrieve
from common.otel import (
    RAG_INDEX_TYPE,
    RAG_RETRIEVAL_SCORES,
    RAG_RETRIEVAL_TOP_K,
    RAG_TENANT_ID,
    get_tracer,
    instrument_fastapi,
    setup_telemetry,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry("retrieval-api")
    await load_secrets()
    # Read replica for query workload; primary reserved for ingestion writes.
    app.state.pool = await create_pool(host=settings.pg_replica_host or settings.pg_host)
    yield
    await app.state.pool.close()


app = FastAPI(title="rag-retrieval-service · retrieval-api", lifespan=lifespan)
instrument_fastapi(app)


def _to_retrieved(c: Candidate) -> RetrievedChunk:
    """Map an internal retrieval Candidate to the API response chunk — one place,
    so the field list can't drift between /v1/search and /v1/answer."""
    return RetrievedChunk(
        document_id=c.document_id,
        source_doc=c.source_doc,
        heading_path=c.heading_path,
        chunk_index=c.chunk_index,
        text=c.text,
        score=c.score,
        created_at=c.created_at,
        page_start=c.page_start,
        page_end=c.page_end,
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up. Cheap, never touches dependencies."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    """Readiness: can we actually serve a query? Proves the DB pool is live.

    A failing readiness pulls the pod out of the Service endpoints without
    killing it (that's liveness's job), so a transient DB blip stops traffic
    rather than triggering a restart loop.
    """
    try:
        async with app.state.pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — surface any pool failure as not-ready
        raise HTTPException(status_code=503, detail="database pool not ready") from exc
    return {"status": "ready"}


@app.post("/v1/answer", response_model=QueryResponse)
async def answer_query(
    req: QueryRequest,
    _claims: dict = Depends(require_scope("query:read")),
) -> QueryResponse:
    """Retrieve, assemble the context under the policy, and generate a grounded,
    cited answer. The surface a human-built app (a compliance dashboard) calls."""
    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute(RAG_TENANT_ID, req.tenant_id)
        span.set_attribute(RAG_RETRIEVAL_TOP_K, req.top_k)
        # The active ANN index is fixed by the schema, not the request.
        span.set_attribute(RAG_INDEX_TYPE, settings.index_type)
        policy = req.assembly_policy or settings.assembly_policy
        hybrid = settings.hybrid_enabled if req.hybrid is None else req.hybrid
        # The assembly policy governs whether rerank runs: top_k_by_fused skips
        # it, the rerank_* policies require it (an explicit request flag wins).
        rerank_on = req.rerank if req.rerank is not None else (policy != "top_k_by_fused")
        span.set_attribute("rag.retrieval.hybrid", hybrid)
        span.set_attribute("rag.retrieval.rerank", rerank_on)
        span.set_attribute("rag.assembly.policy", policy)

        timings: dict[str, float] = {}

        t0 = perf_counter()
        embeddings = await embed_batch([req.query])
        qvec = str(embeddings[0])
        timings["embed"] = (perf_counter() - t0) * 1000

        t0 = perf_counter()
        async with app.state.pool.acquire() as conn:
            candidates = await retrieve(
                conn,
                query=req.query,
                qvec=qvec,
                tenant=req.tenant_id,
                top_k=req.top_k,
                hybrid=hybrid,
                rerank_on=rerank_on,
            )
        timings["retrieve"] = (perf_counter() - t0) * 1000

        chunks = [_to_retrieved(c) for c in candidates]
        span.set_attribute(RAG_RETRIEVAL_SCORES, [c.score for c in chunks])

        t0 = perf_counter()
        assembled = assemble(
            candidates,
            policy=policy,
            token_budget=settings.context_token_budget,
            query=req.query,
            compress_per_chunk_tokens=settings.compress_per_chunk_tokens,
        )
        timings["assemble"] = (perf_counter() - t0) * 1000
        span.set_attribute("rag.assembly.tokens", assembled.tokens)
        span.set_attribute("rag.assembly.chunks_used", assembled.chunks_used)

        t0 = perf_counter()
        answer_text, model = await answer(req.query, assembled.context)
        timings["generate"] = (perf_counter() - t0) * 1000

        return QueryResponse(
            answer=answer_text,
            chunks=chunks,
            model=model,
            backend=settings.generation_backend,
            timings_ms={k: round(v, 1) for k, v in timings.items()},
            assembly_policy=policy,
            context_tokens=assembled.tokens,
            chunks_used=assembled.chunks_used,
        )


@app.post("/query", response_model=QueryResponse, deprecated=True)
async def query_alias(
    req: QueryRequest,
    claims: dict = Depends(require_scope("query:read")),
) -> QueryResponse:
    """Deprecated alias for POST /v1/answer; kept so existing callers don't break."""
    return await answer_query(req, claims)


@app.post("/v1/search", response_model=SearchResponse)
async def search(
    req: SearchRequest,
    _claims: dict = Depends(require_scope("query:read")),
) -> SearchResponse:
    """Retrieval only — hybrid + rerank, no answer generation. The surface an
    agent calls to get evidence to reason over (vs /v1/answer for apps)."""
    with tracer.start_as_current_span("rag_search") as span:
        span.set_attribute(RAG_TENANT_ID, req.tenant_id)
        span.set_attribute(RAG_RETRIEVAL_TOP_K, req.top_k)
        span.set_attribute(RAG_INDEX_TYPE, settings.index_type)
        hybrid = settings.hybrid_enabled if req.hybrid is None else req.hybrid
        rerank_on = settings.rerank_enabled if req.rerank is None else req.rerank
        span.set_attribute("rag.retrieval.hybrid", hybrid)
        span.set_attribute("rag.retrieval.rerank", rerank_on)

        embeddings = await embed_batch([req.query])
        qvec = str(embeddings[0])
        async with app.state.pool.acquire() as conn:
            candidates = await retrieve(
                conn,
                query=req.query,
                qvec=qvec,
                tenant=req.tenant_id,
                top_k=req.top_k,
                hybrid=hybrid,
                rerank_on=rerank_on,
            )
        chunks = [_to_retrieved(c) for c in candidates]
        span.set_attribute(RAG_RETRIEVAL_SCORES, [c.score for c in chunks])
        return SearchResponse(chunks=chunks, hybrid=hybrid, rerank=rerank_on)
