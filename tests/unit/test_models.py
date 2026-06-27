from datetime import datetime, timezone

from common.models import (
    Chunk,
    IngestMessage,
    IngestRequest,
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
)


def test_ingest_request_defaults():
    req = IngestRequest(source_doc="doc.md", content="hello")
    assert req.tenant_id == "default"
    assert req.metadata == {}
    assert req.content_type == "text/markdown"


def test_ingest_message_roundtrip():
    msg = IngestMessage(
        document_id="d1",
        blob_path="default/raw/d1.bin",
        tenant_id="default",
        source_doc="doc.md",
        content_type="text/markdown",
        queued_at=datetime.now(tz=timezone.utc),
    )
    raw = msg.model_dump_json()
    assert IngestMessage.model_validate_json(raw) == msg


def test_query_response_schema():
    rc = RetrievedChunk(
        document_id="d1",
        source_doc="doc.md",
        heading_path="Top",
        chunk_index=0,
        text="hello",
        score=0.92,
    )
    resp = QueryResponse(
        answer="answer text",
        chunks=[rc],
        model="gpt-4o-mini",
        backend="aoai",
    )
    assert resp.backend == "aoai"
    assert resp.chunks[0].score == 0.92


def test_query_request_top_k_default():
    qr = QueryRequest(query="what is X")
    assert qr.top_k == 8


def test_query_request_has_no_index_type():
    # The ANN index is a schema property, not a per-query knob — the field was
    # removed so callers can't pretend to switch it.
    assert "index_type" not in QueryRequest.model_fields


def test_chunk_has_required_columns():
    c = Chunk(
        document_id="d1",
        tenant_id="t1",
        source_doc="doc.md",
        chunk_index=0,
        token_count=10,
        text="hi",
    )
    assert c.heading_path == ""
