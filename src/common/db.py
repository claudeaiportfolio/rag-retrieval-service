"""Postgres connection pool with AAD token auth.

The username comes from the workload identity's principal name (passed via env);
the password is a freshly-issued AAD access token scoped to Postgres. asyncpg
calls the `password=` callback per connection so tokens refresh automatically.
"""

from __future__ import annotations

import asyncpg

from common.azure_clients import credential
from common.config import settings


async def _aad_token() -> str:
    token = await credential().get_token("https://ossrdbms-aad.database.windows.net/.default")
    return token.token


async def create_pool(host: str | None = None, **kwargs) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=host or settings.pg_host,
        port=5432,
        user=settings.pg_user,
        database=settings.pg_database,
        password=_aad_token,
        ssl="require",
        min_size=1,
        max_size=10,
        **kwargs,
    )
