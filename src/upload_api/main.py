"""upload-api: accept document → blob + RQ enqueue (Redis)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from common.azure_clients import blob_service_client
from common.config import load_secrets, settings
from common.models import IngestMessage, IngestRequest
from common.otel import (
    RAG_DOC_ID,
    RAG_TENANT_ID,
    get_tracer,
    instrument_fastapi,
    setup_telemetry,
)
from platform_core.queue import RedisSettings, Retry, get_queue, redis_connection

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

_queue = None


def _get_queue():
    """Lazily build (and cache) the RQ queue on its Redis connection."""
    global _queue
    if _queue is None:
        connection = redis_connection(
            RedisSettings(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                username=settings.redis_username or None,
                password=settings.redis_password or None,
                use_tls=settings.redis_use_tls,
                ssl_ca_certs=settings.redis_ca_path or None,
            )
        )
        _queue = get_queue(settings.rq_queue_name, connection)
    return _queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry("upload-api")
    await load_secrets()
    yield


app = FastAPI(title="rag-retrieval-service · upload-api", lifespan=lifespan)
instrument_fastapi(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    """Readiness: the deps we need to accept an upload are configured.

    upload-api writes the blob then enqueues a job, so it must know both the
    storage account and the Redis queue target before it can serve.
    """
    missing = [
        name
        for name, value in (
            ("storage_account", settings.storage_account),
            ("redis_host", settings.redis_host),
        )
        if not value
    ]
    if missing:
        raise HTTPException(status_code=503, detail=f"unconfigured: {', '.join(missing)}")
    return {"status": "ready"}


@app.post("/documents", status_code=202)
async def ingest_document(req: IngestRequest) -> dict[str, str]:
    if not req.content and not req.source_uri:
        raise HTTPException(status_code=400, detail="content or source_uri required")

    document_id = uuid.uuid4().hex
    blob_path = f"{req.tenant_id}/raw/{document_id}.bin"

    with tracer.start_as_current_span("ingest_document") as span:
        span.set_attribute(RAG_DOC_ID, document_id)
        span.set_attribute(RAG_TENANT_ID, req.tenant_id)
        span.set_attribute("rag.source_doc", req.source_doc)

        body = (req.content or "").encode("utf-8")
        async with blob_service_client(settings.storage_account) as bsc:
            container = bsc.get_container_client(settings.storage_container)
            await container.upload_blob(name=blob_path, data=body, overwrite=True)

        msg_payload = IngestMessage(
            document_id=document_id,
            blob_path=blob_path,
            tenant_id=req.tenant_id,
            source_doc=req.source_doc,
            content_type=req.content_type,
            queued_at=datetime.now(tz=timezone.utc),
            metadata=req.metadata,
        )

        # RQ enqueue is synchronous (a Redis LPUSH) — offload so we don't block
        # the event loop. Transient failures get bounded RQ retries; exhausted /
        # poison jobs land in the FailedJobRegistry (dead-letter).
        await asyncio.to_thread(
            _get_queue().enqueue,
            "embedding_worker.tasks.process_document",
            msg_payload.model_dump(mode="json"),
            retry=Retry(max=3, interval=[10, 30, 60]),
            job_timeout=300,
        )

    logger.info(
        "event=document_queued document_id=%s tenant=%s source=%s",
        document_id,
        req.tenant_id,
        req.source_doc,
    )
    return {"document_id": document_id, "status": "queued"}
