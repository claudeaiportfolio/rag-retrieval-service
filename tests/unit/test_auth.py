"""Pure-logic tests for per-tool scope enforcement.

No network / no JWKS mocking (token verification is exercised in prod E2E);
these cover the scope rules and the authorize() control flow.
"""

import pytest

from common.config import settings
from mcp_server import auth


def test_tool_scopes_cover_every_exposed_tool():
    for tool in ("ingest_document", "query_knowledge"):
        assert tool in auth.TOOL_SCOPES


def test_assert_scope_passes_when_present():
    auth.assert_scope({"scope": "query:read ingest:write"}, "ingest:write")


def test_assert_scope_rejects_when_missing():
    with pytest.raises(auth.AuthError):
        auth.assert_scope({"scope": "query:read"}, "ingest:write")


def test_assert_scope_rejects_empty_claims():
    with pytest.raises(auth.AuthError):
        auth.assert_scope({}, "query:read")


async def test_authorize_skipped_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "auth0_domain", "")
    assert await auth.authorize(None, "ingest_document") == {}


async def test_authorize_requires_token_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "auth0_domain", "example.auth0.com")
    with pytest.raises(auth.AuthError):
        await auth.authorize(None, "query_knowledge")
