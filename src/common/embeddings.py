"""AOAI embedding client backed by Entra ID auth (no API keys).

One module-level client, reused across calls. The Azure AD token provider is
invoked per request by the SDK, so tokens refresh automatically without
rebuilding the client. Transient failures (429/5xx/timeouts) are retried with
exponential backoff, and large batches are split so a single request never
exceeds the deployment's per-call input ceiling.
"""

from __future__ import annotations

import logging

from azure.identity.aio import get_bearer_token_provider
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncAzureOpenAI,
    InternalServerError,
    RateLimitError,
)
from opentelemetry import trace
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from common.azure_clients import credential
from common.config import settings
from common.otel import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_EMBED_DIM = 1536  # text-embedding-3-small
_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
# AOAI accepts up to 2048 inputs/request, but keeping requests bounded caps
# per-request token usage and the blast radius of a single 429.
_MAX_INPUTS_PER_REQUEST = 96

_RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)

_client: AsyncAzureOpenAI | None = None


def _aoai() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=settings.aoai_endpoint,
            azure_deployment=settings.aoai_embedding_deployment,
            azure_ad_token_provider=get_bearer_token_provider(
                credential(), _COGNITIVE_SCOPE
            ),
            api_version="2024-10-21",
        )
    return _client


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def _embed_request(client: AsyncAzureOpenAI, inputs: list[str]):
    return await client.embeddings.create(
        model=settings.aoai_embedding_deployment,
        input=inputs,
    )


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings, sub-batching to stay under request limits."""
    client = _aoai()
    with tracer.start_as_current_span("embed") as span:
        span.set_attribute(GEN_AI_PROVIDER_NAME, "azure.openai")
        span.set_attribute(GEN_AI_REQUEST_MODEL, settings.aoai_embedding_deployment)
        span.set_attribute(GEN_AI_OPERATION_NAME, "embeddings")
        span.set_attribute("rag.embed.batch_size", len(texts))

        embeddings: list[list[float]] = []
        total_tokens = 0
        for start in range(0, len(texts), _MAX_INPUTS_PER_REQUEST):
            sub = texts[start : start + _MAX_INPUTS_PER_REQUEST]
            response = await _embed_request(client, sub)
            embeddings.extend(d.embedding for d in response.data)
            total_tokens += response.usage.prompt_tokens

        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, total_tokens)
        span.set_attribute("rag.embed.requests", -(-len(texts) // _MAX_INPUTS_PER_REQUEST))
        return embeddings


def embedding_dim() -> int:
    return _EMBED_DIM
