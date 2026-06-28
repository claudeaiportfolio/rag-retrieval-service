"""Document extraction seam — bytes (+ content type) → Markdown + page provenance.

A swappable boundary (same philosophy as the LLMProvider seam): the ingest path
depends on the `Extractor` protocol, not on Azure Document Intelligence directly,
so a self-hosted extractor (Docling) can replace it for residency-strict tenants
with no change to chunking or retrieval.

`ExtractedDoc` carries the Markdown *and* an offset→page map, because the
service's promise is "answers with citations back to the source" — every chunk
must know the page(s) it came from, threaded from extraction → chunking → schema
→ the cited answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PageSpan:
    """A character range in the extracted Markdown that came from `page`."""

    page: int
    offset: int
    length: int


@dataclass
class ExtractedDoc:
    markdown: str
    # Ordered offset ranges → page number. Empty for formats without pages
    # (Markdown/plain text), where citations fall back to heading_path.
    pages: list[PageSpan] = field(default_factory=list)

    def page_for_offset(self, offset: int) -> int | None:
        for span in self.pages:
            if span.offset <= offset < span.offset + span.length:
                return span.page
        return None

    def page_range(self, start: int, end: int) -> tuple[int | None, int | None]:
        """First/last page covered by the Markdown range [start, end)."""
        first = self.page_for_offset(start)
        last = self.page_for_offset(max(start, end - 1))
        return first, last


@runtime_checkable
class Extractor(Protocol):
    async def extract(self, blob: bytes, content_type: str) -> ExtractedDoc: ...
