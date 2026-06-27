"""End-to-end smoke: ingest one doc, wait for embed, query, assert.

Drives the public HTTPRoutes — no kubectl needed. Reports a single line per
phase plus a final PASS/FAIL.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import time

import httpx

INGEST_URL = "https://rag-ingest.dev.michaelalinks.com/documents"
QUERY_URL = "https://rag-retrieve.dev.michaelalinks.com/query"
TENANT = "smoke"
DOC = pathlib.Path(__file__).resolve().parents[1] / "corpus/keda-overview.md"
QUESTION = "Can KEDA scale workloads to zero?"
EXPECTED_DOC = "keda-overview.md"


async def main() -> int:
    text = DOC.read_text()
    print(f"ingesting {DOC.name} ({len(text)} bytes) -> {INGEST_URL}")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            INGEST_URL,
            json={
                "content": text,
                "content_type": "text/markdown",
                "source_doc": DOC.name,
                "tenant_id": TENANT,
            },
        )
        resp.raise_for_status()
        doc_id = resp.json().get("document_id", "")
        print(f"queued document_id={doc_id}")

        deadline = time.monotonic() + 240
        last_count = -1
        while time.monotonic() < deadline:
            await asyncio.sleep(8)
            try:
                qr = await client.post(
                    QUERY_URL,
                    json={"query": QUESTION, "tenant_id": TENANT, "top_k": 3},
                )
                qr.raise_for_status()
                chunks = qr.json().get("chunks", [])
                count = len(chunks)
                if count != last_count:
                    print(f"chunks visible: {count}")
                    last_count = count
                if count and chunks[0].get("source_doc") == EXPECTED_DOC:
                    top = chunks[0]
                    print(
                        f"PASS — top hit '{top['source_doc']}' / "
                        f"'{top['heading_path']}' (score {top['score']:.3f})"
                    )
                    print(
                        f"answer: {qr.json().get('answer', '')[:200]!r}"
                    )
                    return 0
            except httpx.HTTPError as exc:
                print(f"query waiting ({exc.__class__.__name__})")

        print("FAIL — timed out waiting for ingestion or top hit not the doc")
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
