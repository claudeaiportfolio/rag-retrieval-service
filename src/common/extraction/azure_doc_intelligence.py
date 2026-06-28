"""Azure AI Document Intelligence extractor (prebuilt-layout, Markdown output).

Handles the hard core of regulated documents — scanned/digital PDFs, tables,
forms — with OCR and, crucially, **page provenance**: `result.pages[].spans`
give the character ranges in the Markdown that belong to each page, which we map
into `ExtractedDoc.pages` so chunks can cite a page.

`from_analyze_result` is a pure function so the parse is unit-tested against a
recorded ADI response without a network call (the live API is paid + async).
Auth is workload identity (no keys) via DefaultAzureCredential.
"""

from __future__ import annotations

from typing import Any

from common.config import settings
from common.extraction.base import ExtractedDoc, PageSpan


def from_analyze_result(result: Any) -> ExtractedDoc:
    """Map an ADI AnalyzeResult (markdown mode) → ExtractedDoc."""
    pages: list[PageSpan] = []
    for page in getattr(result, "pages", None) or []:
        for span in getattr(page, "spans", None) or []:
            pages.append(
                PageSpan(page=page.page_number, offset=span.offset, length=span.length)
            )
    pages.sort(key=lambda s: s.offset)
    return ExtractedDoc(markdown=result.content, pages=pages)


class AzureDocIntelligenceExtractor:
    name = "azure_document_intelligence"

    def __init__(self, endpoint: str | None = None, client: Any | None = None) -> None:
        # `client` is injectable for tests; real client built lazily so importing
        # this module needs no endpoint/credential.
        self._endpoint = endpoint or settings.doc_intelligence_endpoint
        self._client = client

    def _make_client(self) -> Any:
        from azure.ai.documentintelligence.aio import DocumentIntelligenceClient

        from common.azure_clients import credential

        return DocumentIntelligenceClient(self._endpoint, credential())

    async def extract(self, blob: bytes, content_type: str) -> ExtractedDoc:
        from azure.ai.documentintelligence.models import (
            AnalyzeDocumentRequest,
            DocumentContentFormat,
        )

        client = self._client or self._make_client()
        # Close a client we created (not an injected one), so the aio session
        # doesn't leak — one extract per document on the KEDA-scaled worker.
        owns_client = self._client is None
        try:
            poller = await client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=blob),
                output_content_format=DocumentContentFormat.MARKDOWN,
            )
            result = await poller.result()
            return from_analyze_result(result)
        finally:
            if owns_client:
                await client.close()
