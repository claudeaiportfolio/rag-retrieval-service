"""Per-tool MCP scope enforcement, on top of the shared JWT verification.

The generic JWT primitives (`verify_jwt`, `assert_scope`, `AuthError`) live in
`common.auth` so the HTTP API and the MCP server share one implementation. This
module keeps the MCP-specific part: the per-tool scope map and `authorize()`.
"""

from __future__ import annotations

import logging
from typing import Any

from common.auth import AuthError, assert_scope, verify_jwt
from common.config import settings

logger = logging.getLogger(__name__)

# Per-tool scope requirements. Aligned with the portfolio-infra Auth0 resource
# server reservation for `https://rag.dev.michaelalinks.com`.
TOOL_SCOPES: dict[str, str] = {
    "ingest_document": "ingest:write",
    "query_knowledge": "query:read",
    "search_knowledge": "query:read",
    "reindex": "admin:reindex",
}

__all__ = ["AuthError", "TOOL_SCOPES", "assert_scope", "authorize", "verify_jwt"]


async def authorize(authorization: str | None, tool_name: str) -> dict[str, Any]:
    """Verify the bearer token and assert the scope required for `tool_name`.

    `authorization` is the raw `Authorization` header value. Returns the decoded
    claims on success; raises `AuthError` otherwise. When `auth0_domain` is unset
    (local dev), authorization is skipped so the stack runs without Auth0.
    """
    if not settings.auth0_domain:
        logger.debug("event=auth_skipped reason=no_auth0_domain tool=%s", tool_name)
        return {}
    if not authorization:
        raise AuthError("missing bearer token")
    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    claims = await verify_jwt(token)
    required = TOOL_SCOPES.get(tool_name)
    if required:
        assert_scope(claims, required)
    return claims
