from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Request body for POST /documents — accepted by upload-api."""

    source_uri: str | None = None
    content: str | None = None
    content_type: str = "text/markdown"
    tenant_id: str = "default"
    source_doc: str
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestMessage(BaseModel):
    """RQ ingest job — upload-api → embedding-worker."""

    document_id: str
    blob_path: str
    tenant_id: str
    source_doc: str
    content_type: str
    queued_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)


class Chunk(BaseModel):
    document_id: str
    tenant_id: str
    source_doc: str
    heading_path: str = ""
    chunk_index: int
    token_count: int
    text: str


class QueryRequest(BaseModel):
    query: str
    tenant_id: str = "default"
    top_k: int = 8
    # Per-request overrides of the configured retrieval mode. None = use the
    # service default (settings.hybrid_enabled / settings.rerank_enabled). The
    # rerank ON/OFF eval drives these to measure the recall@k and p95 delta.
    hybrid: bool | None = None
    rerank: bool | None = None
    # Context-assembly policy override (top_k_by_fused | rerank_then_top_k |
    # rerank_then_compress). None = service default. Drives the assembly table.
    assembly_policy: Literal[
        "top_k_by_fused", "rerank_then_top_k", "rerank_then_compress"
    ] | None = None
    # NB: the ANN index (HNSW vs IVFFlat) is a property of the `chunks` table,
    # not something a single query can switch — pgvector picks the index for the
    # `<=>` operator automatically. The configured index lives in
    # `settings.index_type` and is recorded on the retrieval span for analysis.


class RetrievedChunk(BaseModel):
    document_id: str
    source_doc: str
    heading_path: str
    chunk_index: int
    text: str
    score: float
    created_at: datetime | None = None  # freshness signal (ingest timestamp)


class QueryResponse(BaseModel):
    answer: str
    chunks: list[RetrievedChunk]
    model: str
    backend: Literal["aoai", "anthropic"]
    # Assembly observability — the inputs to the policy × (accuracy, tokens,
    # latency) table.
    assembly_policy: str = "rerank_then_top_k"
    context_tokens: int = 0
    chunks_used: int = 0
    # Per-stage wall-clock (ms): embed / retrieve / assemble / generate. The
    # "where does the latency go" attribution the load test aggregates into
    # per-stage p50/p95/p99.
    timings_ms: dict[str, float] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    """POST /v1/search — retrieval only, no answer generation. The interface an
    agent (e.g. piece 2's diligence agent) calls to get evidence to reason over."""

    query: str
    tenant_id: str = "default"
    top_k: int = 8
    hybrid: bool | None = None
    rerank: bool | None = None


class SearchResponse(BaseModel):
    chunks: list[RetrievedChunk]
    hybrid: bool
    rerank: bool
