"""Auth dependency + versioned-surface tests (no DB / no network)."""

import pytest
from fastapi import HTTPException

from common import auth
from common.config import settings


async def test_require_scope_skips_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "auth0_domain", "")
    dep = auth.require_scope("query:read")
    assert await dep(authorization=None) == {}


async def test_require_scope_401_without_token(monkeypatch):
    monkeypatch.setattr(settings, "auth0_domain", "example.auth0.com")
    dep = auth.require_scope("query:read")
    with pytest.raises(HTTPException) as excinfo:
        await dep(authorization=None)
    assert excinfo.value.status_code == 401


def test_openapi_exposes_versioned_endpoints():
    from retrieval_api.main import app

    paths = app.openapi()["paths"]
    assert "/v1/search" in paths
    assert "/v1/answer" in paths
    # /query stays as a deprecated alias.
    assert paths["/query"]["post"].get("deprecated") is True
