"""Auth0 JWT verification + a FastAPI scope dependency.

The Envoy Gateway verifies the token at the edge (a SecurityPolicy CR), so
unauthenticated requests never reach a pod. This module is the in-app, per-route
*scope* check — the gateway proves the token is valid; `require_scope` /
`assert_scope` prove the caller holds the scope a given route or tool requires
(e.g. `query:read` vs `ingest:write`).

Centralised here so the HTTP API (retrieval-api) and the MCP server share one
JWT implementation instead of each rolling their own. PyJWT (not python-jose,
which is unmaintained and has had algorithm-confusion CVEs); `PyJWKClient` caches
the Auth0 JWKS with a TTL so key rotation is picked up without a pod restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from common.config import settings

logger = logging.getLogger(__name__)

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
    """Validate `token` against the Auth0 JWKS; return the decoded claims.

    The signing-key fetch runs in a worker thread because `PyJWKClient` is sync.
    """
    if not settings.auth0_domain:
        raise AuthError("auth0_domain not configured")
    try:
        signing_key = await asyncio.to_thread(_client().get_signing_key_from_jwt, token)
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


def require_scope(required: str):
    """FastAPI dependency: verify the bearer token and assert `required` scope.

    When `auth0_domain` is unset (local dev) authorization is skipped so the
    stack runs without Auth0. Returns the decoded claims on success.
    """

    async def _dependency(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        if not settings.auth0_domain:
            logger.debug("event=auth_skipped reason=no_auth0_domain scope=%s", required)
            return {}
        if not authorization:
            raise HTTPException(status_code=401, detail="missing bearer token")
        token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
        try:
            claims = await verify_jwt(token)
            assert_scope(claims, required)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return claims

    return _dependency
