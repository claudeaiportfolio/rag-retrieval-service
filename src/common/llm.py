"""Grounded answer generation via the shared `llm-provider` seam.

This is the RAG service's *only* LLM call. Provider selection is config-driven
(`settings.generation_backend`): Claude (public Anthropic) or Azure OpenAI
(AAD-authed). Both run through the same `LLMProvider` protocol — only client
construction differs (the seam's OpenAI impl takes an injected client, so the
AAD-authed `AsyncAzureOpenAI` drops straight in). The seam owns the message /
tool-result / response translation; this module keeps the app concerns: the
AAD client, the retry policy, and the GenAI chat span (whose `gen_ai.usage.*`
attributes feed the token-cost panel).
"""

from __future__ import annotations

import logging
from typing import Any

from anthropic import APIConnectionError as AnthropicConnectionError
from anthropic import APITimeoutError as AnthropicTimeoutError
from anthropic import InternalServerError as AnthropicInternalServerError
from anthropic import RateLimitError as AnthropicRateLimitError
from llm_provider import Message, ProviderConfig
from llm_provider.anthropic_provider import AnthropicProvider
from llm_provider.base import LLMProvider
from llm_provider.openai_provider import OpenAIProvider
from openai import APIConnectionError as OpenAIConnectionError
from openai import APITimeoutError as OpenAITimeoutError
from openai import InternalServerError as OpenAIInternalServerError
from openai import RateLimitError as OpenAIRateLimitError
from opentelemetry import trace
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from common.config import settings
from common.otel import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
_MAX_TOKENS = 1024

# Transient failures from either backend; only one is active per call, but both
# SDKs are dependencies so importing both exception sets is safe.
_TRANSIENT = (
    AnthropicRateLimitError,
    AnthropicConnectionError,
    AnthropicTimeoutError,
    AnthropicInternalServerError,
    OpenAIRateLimitError,
    OpenAIConnectionError,
    OpenAITimeoutError,
    OpenAIInternalServerError,
)

# (provider, model, otel_provider_label), built once and reused.
_provider_cache: tuple[LLMProvider, str, str] | None = None
# The SDK client we created (Anthropic or AzureOpenAI), kept so aclose() can shut
# it down on app shutdown without reaching into the seam provider's internals.
_client_cache: Any = None


def _backoff() -> dict:
    return dict(
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )


def _build_provider() -> tuple[LLMProvider, str, str]:
    global _client_cache
    if settings.generation_backend == "anthropic":
        from anthropic import AsyncAnthropic

        anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        _client_cache = anthropic_client
        return AnthropicProvider(client=anthropic_client), settings.anthropic_model, "anthropic"

    # Azure OpenAI: AAD token provider (no key), same chat-completions surface
    # the seam's OpenAI impl speaks.
    from azure.identity.aio import get_bearer_token_provider
    from openai import AsyncAzureOpenAI

    from common.azure_clients import credential

    aoai_client = AsyncAzureOpenAI(
        azure_endpoint=settings.aoai_endpoint,
        azure_deployment=settings.aoai_chat_deployment,
        azure_ad_token_provider=get_bearer_token_provider(credential(), _COGNITIVE_SCOPE),
        api_version="2024-10-21",
    )
    _client_cache = aoai_client
    return OpenAIProvider(client=aoai_client), settings.aoai_chat_deployment, "azure.openai"


async def aclose() -> None:
    """Close the underlying provider client. Call on app shutdown (idempotent)."""
    global _provider_cache, _client_cache
    if _client_cache is not None:
        await _client_cache.close()
        _client_cache = None
    _provider_cache = None


def _provider() -> tuple[LLMProvider, str, str]:
    global _provider_cache
    if _provider_cache is None:
        _provider_cache = _build_provider()
    return _provider_cache


async def answer(question: str, context: str) -> tuple[str, str]:
    """Return (answer_text, model_id) for the configured backend, via the seam."""
    provider, model, label = _provider()
    config = ProviderConfig(model=model, system=_SYSTEM_PROMPT, max_tokens=_MAX_TOKENS)
    messages = [Message(role="user", content=_user_prompt(question, context))]

    @retry(retry=retry_if_exception_type(_TRANSIENT), **_backoff())
    async def _call():
        return await provider.complete(messages, config=config)

    with tracer.start_as_current_span("chat") as span:
        span.set_attribute(GEN_AI_PROVIDER_NAME, label)
        span.set_attribute(GEN_AI_REQUEST_MODEL, model)
        span.set_attribute(GEN_AI_OPERATION_NAME, "chat")
        completion = await _call()
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, completion.usage.input_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, completion.usage.output_tokens)
        span.set_attribute(GEN_AI_RESPONSE_MODEL, completion.model)
        return completion.text, completion.model


_SYSTEM_PROMPT = (
    "You answer questions using only the provided retrieval context. "
    "Cite the source heading path for every claim. If the context does not "
    "contain the answer, say so plainly — do not guess."
)


def _user_prompt(question: str, context: str) -> str:
    return f"<context>\n{context}\n</context>\n\nQuestion: {question}"
