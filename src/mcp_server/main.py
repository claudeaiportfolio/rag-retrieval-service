"""mcp-server: public MCP endpoint fronting upload-api + retrieval-api.

Tools:
  - ingest_document(content, source_doc, tenant_id?) → document_id
  - query_knowledge(query, tenant_id?, top_k?) → {answer, chunks}  (composed answer)
  - search_knowledge(query, tenant_id?, top_k?) → {chunks}  (retrieval only, for agents)

Authentication is enforced by `src/mcp_server/auth.py` (Auth0 JWT).
"""

from __future__ import annotations

import logging
import os

import httpx
from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from common.config import load_secrets
from common.models import IngestRequest, QueryRequest, SearchRequest
from common.otel import MCP_METHOD_NAME, get_tracer, setup_telemetry
from mcp_server.auth import AuthError, authorize

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _bearer(ctx: Context | None) -> str | None:
    """Pull the Authorization header off the in-flight HTTP request, if any."""
    if ctx is None:
        return None
    request = getattr(ctx.request_context, "request", None)
    if request is None:
        return None
    return request.headers.get("authorization")

UPLOAD_API = os.environ.get("UPLOAD_API_URL", "http://upload-api.ingestion.svc.cluster.local:8080")
RETRIEVAL_API = os.environ.get("RETRIEVAL_API_URL", "http://retrieval-api.query.svc.cluster.local:8080")

mcp = FastMCP("rag-retrieval-service")


# Health endpoints live outside the MCP protocol (custom_route → unauthenticated),
# so kubelet probes don't need an Auth0 token. Liveness is a bare process check;
# readiness confirms the downstream APIs the server proxies are configured.
@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(_request: Request) -> JSONResponse:
    if not UPLOAD_API or not RETRIEVAL_API:
        return JSONResponse({"status": "not ready"}, status_code=503)
    return JSONResponse({"status": "ready"})


@mcp.tool()
async def ingest_document(
    content: str,
    source_doc: str,
    tenant_id: str = "default",
    ctx: Context | None = None,
) -> dict[str, str]:
    """Queue a document for embedding + indexing. Returns document_id."""
    with tracer.start_as_current_span("mcp.ingest_document") as span:
        span.set_attribute(MCP_METHOD_NAME, "ingest_document")
        try:
            await authorize(_bearer(ctx), "ingest_document")
        except AuthError as exc:
            span.set_attribute("rag.auth.denied", True)
            raise ValueError(f"unauthorized: {exc}") from exc
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{UPLOAD_API}/documents",
                json=IngestRequest(
                    content=content,
                    source_doc=source_doc,
                    tenant_id=tenant_id,
                ).model_dump(),
            )
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def query_knowledge(
    query: str,
    tenant_id: str = "default",
    top_k: int = 8,
    ctx: Context | None = None,
) -> dict:
    """Search the indexed corpus and return a grounded answer with citations."""
    with tracer.start_as_current_span("mcp.query_knowledge") as span:
        span.set_attribute(MCP_METHOD_NAME, "query_knowledge")
        try:
            await authorize(_bearer(ctx), "query_knowledge")
        except AuthError as exc:
            span.set_attribute("rag.auth.denied", True)
            raise ValueError(f"unauthorized: {exc}") from exc
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{RETRIEVAL_API}/v1/answer",
                json=QueryRequest(query=query, tenant_id=tenant_id, top_k=top_k).model_dump(),
            )
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def search_knowledge(
    query: str,
    tenant_id: str = "default",
    top_k: int = 8,
    ctx: Context | None = None,
) -> dict:
    """Retrieve relevant chunks (hybrid + rerank) WITHOUT generating an answer.

    Use this to get evidence to reason over yourself; use query_knowledge for a
    composed, cited answer. This is the agent-facing half of "one service, the
    right interface per consumer".
    """
    with tracer.start_as_current_span("mcp.search_knowledge") as span:
        span.set_attribute(MCP_METHOD_NAME, "search_knowledge")
        try:
            await authorize(_bearer(ctx), "search_knowledge")
        except AuthError as exc:
            span.set_attribute("rag.auth.denied", True)
            raise ValueError(f"unauthorized: {exc}") from exc
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{RETRIEVAL_API}/v1/search",
                json=SearchRequest(query=query, tenant_id=tenant_id, top_k=top_k).model_dump(),
            )
            response.raise_for_status()
            return response.json()


async def _startup() -> None:
    setup_telemetry("mcp-server")
    await load_secrets()
    logger.info("event=mcp_starting upload=%s retrieval=%s", UPLOAD_API, RETRIEVAL_API)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_startup())
    mcp.run(transport="streamable-http")
