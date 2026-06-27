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
                content = (await downloader.readall()).decode("utf-8", errors="replace")

            chunks = chunk_document(
                document_id=msg.document_id,
                tenant_id=msg.tenant_id,
                source_doc=msg.source_doc,
                text=content,
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


async def _insert_chunks(pool: Any, chunks: Any, embeddings: Any) -> None:
    rows = [
        (
            c.document_id,
            c.tenant_id,
            c.source_doc,
            c.heading_path,
            c.chunk_index,
            c.token_count,
            c.text,
            str(emb),
            hashlib.sha256(c.text.encode("utf-8")).hexdigest(),
        )
        for c, emb in zip(chunks, embeddings, strict=True)
    ]
    # ON CONFLICT DO NOTHING dedups on (tenant_id, content_hash): re-ingesting the
    # same chunk text is a no-op rather than a duplicate that corrupts retrieval.
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO chunks (document_id, tenant_id, source_doc, heading_path,
                                chunk_index, token_count, text, embedding, content_hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9)
            ON CONFLICT (tenant_id, content_hash) DO NOTHING
            """,
            rows,
        )
