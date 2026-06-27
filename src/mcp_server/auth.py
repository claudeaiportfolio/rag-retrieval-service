"""Auth0 JWT verification (PyJWT + JWKS with TTL caching).

Public JWT enforcement lives at the Envoy Gateway via a SecurityPolicy CR
(`k8s/query/securitypolicy.yaml`), so unauthenticated requests are rejected
before they reach a pod. This module is the in-app, per-tool *scope* check —
the gateway proves the token is valid; `authorize()` proves the caller holds
the scope a given tool requires (e.g. `ingest:write` vs `query:read`).

PyJWT (not python-jose, which is unmaintained and has had algorithm-confusion
CVEs). `PyJWKClient` caches the Auth0 JWKS with a TTL, so key rotation is picked
up automatically instead of breaking until a pod restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from common.config import settings

logger = logging.getLogger(__name__)

# Per-tool scope requirements. Aligned with the portfolio-infra Auth0 resource
# server reservation for `https://rag.dev.michaelalinks.com`.
TOOL_SCOPES: dict[str, str] = {
    "ingest_document": "ingest:write",
    "query_knowledge": "query:read",
    "reindex": "admin:reindex",
}

# Seconds before the cached JWK Set expires and is refetched. Picks up Auth0
# signing-key rotation without a pod restart.
_JWKS_TTL_SECONDS = 3600

_jwks_client: PyJWKClient | None = None


class AuthError(Exception):
    """Token is missing, invalid, or lacks the required scope."""


def _client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=_JWKS_TTL_SECONDS)
    return _jwks_client


async def verify_jwt(token: str) -> dict[str, Any]:
    """Validate `token` against the Auth0 JWKS. Returns the decoded claims.

    Raises `AuthError` on any failure. The signing-key fetch is run in a worker
    thread because `PyJWKClient` is synchronous.
    """
    if not settings.auth0_domain:
        raise AuthError("auth0_domain not configured")
    try:
        signing_key = await asyncio.to_thread(
            _client().get_signing_key_from_jwt, token
        )
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except (PyJWTError, ValueError) as exc:
        raise AuthError(f"token verification failed: {exc}") from exc


def assert_scope(claims: dict[str, Any], required: str) -> None:
    """Raise `AuthError` if `required` is not among the token's scopes."""
    scopes = (claims.get("scope") or "").split()
    if required not in scopes:
        raise AuthError(f"missing required scope: {required}")


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
