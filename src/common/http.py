"""Shared HTTP resilience — one definition of "transient fault" and the retry
policy, so the app (reranker client) and the eval/load-test harnesses don't each
copy-paste the same tenacity boilerplate.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Transient transport faults worth retrying. A 4xx/5xx status is a contract/server
# error and is deliberately NOT included (httpx.HTTPStatusError).
TRANSIENT_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
)


def transient_retry(attempts: int = 3):
    """Retry decorator for the transient set, with exponential backoff."""
    return retry(
        retry=retry_if_exception_type(TRANSIENT_HTTP_ERRORS),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
