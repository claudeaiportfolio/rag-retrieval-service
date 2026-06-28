"""embedding-worker RQ task: chunk → embed → pgvector insert.

`process_document` is the RQ job entrypoint (sync); it runs the async pipeline
in a fresh event loop. Poison jobs (schema/contract failures) are logged and
re-raised so RQ records the failure in the FailedJobRegistry (dead-letter
equivalent); transient failures are absorbed by in-call `tenacity` retries and,
beyond that, RQ's bounded `Retry` set at enqueue time.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from pydantic import ValidationError

from common.azure_clients import blob_service_client
from common.chunking import chunk_document
from common.extraction import get_extractor
from common.config import settings
from common.db import create_pool
from common.embeddings import embed_batch
from common.models import IngestMessage
from common.otel import (
    RAG_CHUNK_COUNT,
    RAG_DOC_ID,
    RAG_TENANT_ID,
    get_tracer,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def is_poison(exc: BaseException) -> bool:
    """A poison message can never succeed on retry — dead-letter it immediately.

    Schema/parse failures (`ValidationError`) are the canonical case: the body
    is malformed or out of contract, so retrying just rebounds it forever.
    Everything else (blob 5xx, DB hiccup, embedding 429) is treated as transient.
    """
    return isinstance(exc, ValidationError)


def process_document(payload: dict[str, Any]) -> None:
    """RQ job entrypoint: run the async ingestion pipeline for one document."""
    try:
        asyncio.run(_process(payload))
    except Exception as exc:
        if is_poison(exc):
            logger.error(
                "event=message_dead_lettered reason=validation_error doc=%s err=%s",
                payload.get("document_id", "?"),
                str(exc)[:200],
            )
        else:
            logger.exception("event=message_failed action=retry")
        raise


async def _process(payload: dict[str, Any]) -> None:
    msg = IngestMessage.model_validate(payload)
    pool = await create_pool()
    try:
        with tracer.start_as_current_span("process_document") as span:
            span.set_attribute(RAG_DOC_ID, msg.document_id)
            span.set_attribute(RAG_TENANT_ID, msg.tenant_id)
            span.set_attribute("rag.source_doc", msg.source_doc)

            async with blob_service_client(settings.storage_account) as bsc:
                blob = bsc.get_blob_client(
                    container=settings.storage_container,
                    blob=msg.blob_path,
                )
                downloader = await blob.download_blob()
                raw = await downloader.readall()

            # Extract by content type: Markdown/text passes through; PDFs/Office
            # go through Document Intelligence (OCR + tables + page provenance).
            extracted = await get_extractor(msg.content_type).extract(raw, msg.content_type)
            span.set_attribute("rag.extractor.pages", len(extracted.pages))
            chunks = chunk_document(
                document_id=msg.document_id,
                tenant_id=msg.tenant_id,
                source_doc=msg.source_doc,
                text=extracted.markdown,
                pages=extracted.pages,
                strategy=settings.chunking_strategy,
                chunk_size_tokens=settings.chunk_size_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            span.set_attribute(RAG_CHUNK_COUNT, len(chunks))
            if not chunks:
                logger.warning("event=no_chunks document_id=%s", msg.document_id)
                return

            embeddings = await embed_batch([c.text for c in chunks])
            await _insert_chunks(pool, chunks, embeddings)
            logger.info(
                "event=document_indexed document_id=%s chunks=%d",
                msg.document_id,
                len(chunks),
            )
    finally:
        await pool.close()


# Single source of truth for the chunks INSERT: column -> value extractor, in
# insert order. The column list, the placeholders (incl. the ::vector cast), and
# the row tuples are all derived from this — add a column in one place and they
# stay in sync, instead of hand-numbering $1..$N across three spots.
_CHUNK_COLUMNS: dict[str, Any] = {
    "document_id": lambda c, emb: c.document_id,
    "tenant_id": lambda c, emb: c.tenant_id,
    "source_doc": lambda c, emb: c.source_doc,
    "heading_path": lambda c, emb: c.heading_path,
    "chunk_index": lambda c, emb: c.chunk_index,
    "token_count": lambda c, emb: c.token_count,
    "text": lambda c, emb: c.text,
    "embedding": lambda c, emb: str(emb),
    "content_hash": lambda c, emb: hashlib.sha256(c.text.encode("utf-8")).hexdigest(),
    "page_start": lambda c, emb: c.page_start,
    "page_end": lambda c, emb: c.page_end,
}
_VECTOR_COLUMNS = {"embedding"}

# ON CONFLICT DO NOTHING dedups on (tenant_id, content_hash): re-ingesting the
# same chunk text is a no-op rather than a duplicate that corrupts retrieval.
_INSERT_CHUNKS_SQL = (
    "INSERT INTO chunks ({cols}) VALUES ({vals}) "
    "ON CONFLICT (tenant_id, content_hash) DO NOTHING"
).format(
    cols=", ".join(_CHUNK_COLUMNS),
    vals=", ".join(
        f"${i}::vector" if col in _VECTOR_COLUMNS else f"${i}"
        for i, col in enumerate(_CHUNK_COLUMNS, start=1)
    ),
)


async def _insert_chunks(pool: Any, chunks: Any, embeddings: Any) -> None:
    rows = [
        tuple(extract(c, emb) for extract in _CHUNK_COLUMNS.values())
        for c, emb in zip(chunks, embeddings, strict=True)
    ]
    async with pool.acquire() as conn:
        await conn.executemany(_INSERT_CHUNKS_SQL, rows)
