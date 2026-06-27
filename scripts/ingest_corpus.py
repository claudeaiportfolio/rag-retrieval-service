"""Push every file in corpus/ to upload-api.

Hits the public upload-api HTTPRoute when UPLOAD_API_URL is set, otherwise
falls back to the in-cluster ClusterIP DNS (which only works when the script
runs inside the AKS cluster — Layer 1 CI uses the public URL).
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import httpx

UPLOAD_API_URL = os.environ.get(
    "UPLOAD_API_URL", "https://rag-ingest.dev.michaelalinks.com"
)
TENANT_ID = os.environ.get("INGEST_TENANT_ID", "evals")


async def ingest_one(client: httpx.AsyncClient, path: pathlib.Path) -> None:
    body = path.read_text(encoding="utf-8")
    response = await client.post(
        f"{UPLOAD_API_URL}/documents",
        json={
            "content": body,
            "content_type": "text/markdown",
            "source_doc": path.name,
            "tenant_id": TENANT_ID,
            "metadata": {"corpus_path": str(path.relative_to(pathlib.Path.cwd()))},
        },
        timeout=60,
    )
    response.raise_for_status()
    document_id = response.json().get("document_id", "")
    print(f"queued {path.name} → {document_id}")


async def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    corpus = root / "corpus"
    # Recursive so a nested layout still ingests; skip the provenance README.
    files = sorted(p for p in corpus.rglob("*.md") if p.name.lower() != "readme.md")
    if not files:
        print(f"no .md files in {corpus}", file=sys.stderr)
        return 1
    async with httpx.AsyncClient() as client:
        for path in files:
            try:
                await ingest_one(client, path)
            except httpx.HTTPError as exc:
                print(f"failed {path.name}: {exc}", file=sys.stderr)
                return 2
    print(f"\nqueued {len(files)} documents to {UPLOAD_API_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
