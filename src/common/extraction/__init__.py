"""Document extraction: bytes (+ content type) → Markdown + page provenance.

    from common.extraction import get_extractor
    doc = await get_extractor(content_type).extract(blob, content_type)
    # doc.markdown, doc.pages (offset→page for citations)
"""

from __future__ import annotations

from common.extraction.azure_doc_intelligence import AzureDocIntelligenceExtractor
from common.extraction.base import ExtractedDoc, Extractor, PageSpan
from common.extraction.factory import get_extractor
from common.extraction.passthrough import PassthroughExtractor

__all__ = [
    "AzureDocIntelligenceExtractor",
    "ExtractedDoc",
    "Extractor",
    "PageSpan",
    "PassthroughExtractor",
    "get_extractor",
]
