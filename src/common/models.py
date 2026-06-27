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
    """Service Bus message — upload-api → embedding-worker."""

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


class QueryResponse(BaseModel):
    answer: str
    chunks: list[RetrievedChunk]
    model: str
    backend: Literal["aoai", "anthropic"]
