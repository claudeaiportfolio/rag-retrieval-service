"""Passthrough extractor for already-text formats (Markdown / plain text).

No conversion, no page provenance (these formats have no pages) — citations fall
back to heading_path. This is the path the curated Markdown corpus uses, so it
costs nothing and keeps the existing behaviour exact.
"""

from __future__ import annotations

from common.extraction.base import ExtractedDoc


class PassthroughExtractor:
    name = "passthrough"

    async def extract(self, blob: bytes, content_type: str) -> ExtractedDoc:
        return ExtractedDoc(markdown=blob.decode("utf-8", errors="replace"), pages=[])
