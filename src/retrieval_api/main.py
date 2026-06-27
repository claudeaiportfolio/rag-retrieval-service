"""retrieval-api: query → embed → vector search → LLM answer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from common.config import load_secrets, settings
from common.db import create_pool
from common.embeddings import embed_batch
from common.llm import answer
from common.models import QueryRequest, QueryResponse, RetrievedChunk
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


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute(RAG_TENANT_ID, req.tenant_id)
        span.set_attribute(RAG_RETRIEVAL_TOP_K, req.top_k)
        # The active ANN index is fixed by the schema, not the request.
        span.set_attribute(RAG_INDEX_TYPE, settings.index_type)

        embeddings = await embed_batch([req.query])
        qvec = embeddings[0]

        pool = app.state.pool
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT document_id, source_doc, heading_path, chunk_index, text,
                       1 - (embedding <=> $1::vector) AS score
                FROM chunks
                WHERE tenant_id = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                str(qvec),
                req.tenant_id,
                req.top_k,
            )

        chunks = [
            RetrievedChunk(
                document_id=r["document_id"],
                source_doc=r["source_doc"],
                heading_path=r["heading_path"],
                chunk_index=r["chunk_index"],
                text=r["text"],
                score=float(r["score"]),
            )
            for r in rows
        ]
        span.set_attribute(RAG_RETRIEVAL_SCORES, [c.score for c in chunks])

        context = "\n\n".join(
            f"[{c.source_doc} :: {c.heading_path}]\n{c.text}" for c in chunks
        )
        answer_text, model = await answer(req.query, context)

        return QueryResponse(
            answer=answer_text,
            chunks=chunks,
            model=model,
            backend=settings.generation_backend,
        )
