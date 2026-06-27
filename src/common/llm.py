"""Config-switchable chat completion: Anthropic or Azure OpenAI.

Clients are built once and reused; AAD tokens for the AOAI path refresh
automatically via the token provider. Transient failures (429/5xx/timeouts)
are retried with exponential backoff on both backends.
"""

from __future__ import annotations

import logging

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

_anthropic_client = None
_aoai_client = None


def _backoff():
    return dict(
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )


async def answer(question: str, context: str) -> tuple[str, str]:
    """Return (answer_text, model_id). Backend chosen via settings.generation_backend."""
    if settings.generation_backend == "anthropic":
        return await _answer_anthropic(question, context)
    return await _answer_aoai(question, context)


def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic

        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


async def _answer_anthropic(question: str, context: str) -> tuple[str, str]:
    from anthropic import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

    client = _anthropic()
    model = settings.anthropic_model

    @retry(
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
        ),
        **_backoff(),
    )
    async def _call():
        return await client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_prompt(question, context)}],
        )

    with tracer.start_as_current_span("chat") as span:
        span.set_attribute(GEN_AI_PROVIDER_NAME, "anthropic")
        span.set_attribute(GEN_AI_REQUEST_MODEL, model)
        span.set_attribute(GEN_AI_OPERATION_NAME, "chat")
        msg = await _call()
        text = "".join(block.text for block in msg.content if block.type == "text")
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, msg.usage.input_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, msg.usage.output_tokens)
        span.set_attribute(GEN_AI_RESPONSE_MODEL, msg.model)
        return text, msg.model


def _aoai():
    global _aoai_client
    if _aoai_client is None:
        from azure.identity.aio import get_bearer_token_provider
        from openai import AsyncAzureOpenAI

        from common.azure_clients import credential

        _aoai_client = AsyncAzureOpenAI(
            azure_endpoint=settings.aoai_endpoint,
            azure_deployment=settings.aoai_chat_deployment,
            azure_ad_token_provider=get_bearer_token_provider(
                credential(), _COGNITIVE_SCOPE
            ),
            api_version="2024-10-21",
        )
    return _aoai_client


async def _answer_aoai(question: str, context: str) -> tuple[str, str]:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

    client = _aoai()

    @retry(
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
        ),
        **_backoff(),
    )
    async def _call():
        return await client.chat.completions.create(
            model=settings.aoai_chat_deployment,
            max_tokens=_MAX_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, context)},
            ],
        )

    with tracer.start_as_current_span("chat") as span:
        span.set_attribute(GEN_AI_PROVIDER_NAME, "azure.openai")
        span.set_attribute(GEN_AI_REQUEST_MODEL, settings.aoai_chat_deployment)
        span.set_attribute(GEN_AI_OPERATION_NAME, "chat")
        response = await _call()
        text = response.choices[0].message.content or ""
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, response.usage.prompt_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, response.usage.completion_tokens)
        span.set_attribute(GEN_AI_RESPONSE_MODEL, response.model)
        return text, response.model


_SYSTEM_PROMPT = (
    "You answer questions using only the provided retrieval context. "
    "Cite the source heading path for every claim. If the context does not "
    "contain the answer, say so plainly — do not guess."
)


def _user_prompt(question: str, context: str) -> str:
    return f"<context>\n{context}\n</context>\n\nQuestion: {question}"
