"""One-shot Postgres bootstrap: CREATE EXTENSION vector + apply schema.sql.

Auths via AAD token from the active az session (works locally and in CI
after azure/login).
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import asyncpg
from azure.identity.aio import DefaultAzureCredential


async def main() -> int:
    # No identifying defaults baked in — host/user come from the environment
    # (set by the terraform-postdeploy workflow from terraform outputs).
    host = os.environ["PG_HOST"]
    user = os.environ["PG_USER"]
    database = os.environ.get("PG_DATABASE", "rag")
    # Comma-separated workload principal names to GRANT chunks access to.
    # Derived from terraform output; empty → skip the grant loop.
    principals = [
        p.strip() for p in os.environ.get("WORKLOAD_DB_PRINCIPALS", "").split(",") if p.strip()
    ]

    cred = DefaultAzureCredential()
    token = await cred.get_token("https://ossrdbms-aad.database.windows.net/.default")
    await cred.close()

    conn = await asyncpg.connect(
        host=host,
        port=5432,
        user=user,
        database=database,
        password=token.token,
        ssl="require",
    )
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("CREATE EXTENSION vector — ok")

        schema_path = pathlib.Path(__file__).resolve().parents[1] / "src/common/schema.sql"
        sql = schema_path.read_text()
        await conn.execute(sql)
        print("schema applied —", schema_path.name)

        # Workload UAMIs are already registered as Entra admins on the
        # server (see terraform module.postgres.workload_admins). Plain
        # GRANTs are still needed so the non-admin grants exist.
        for name in principals:
            try:
                await conn.execute(
                    f'GRANT SELECT, INSERT, UPDATE ON TABLE chunks TO "{name}";'
                )
                await conn.execute(
                    f'GRANT USAGE, SELECT ON SEQUENCE chunks_id_seq TO "{name}";'
                )
                print(f"granted chunks access: {name}")
            except Exception as exc:
                print(f"grant failed for {name}: {exc}")

        rows = await conn.fetch("SELECT COUNT(*) AS n FROM chunks;")
        print(f"chunks row count: {rows[0]['n']}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
