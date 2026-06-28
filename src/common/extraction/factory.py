"""Route a document to the right extractor by content type.

Markdown / plain text → passthrough (no extraction cost). Everything else
(PDF, Office, images) → Azure Document Intelligence. The split keeps the curated
Markdown corpus free and reserves the paid OCR path for documents that need it.
Swap ADI for a self-hosted Docling extractor here for residency-strict tenants.
"""

from __future__ import annotations

from common.extraction.azure_doc_intelligence import AzureDocIntelligenceExtractor
from common.extraction.base import Extractor
from common.extraction.passthrough import PassthroughExtractor

_PASSTHROUGH_TYPES = {"", "text/markdown", "text/plain", "text/x-markdown"}


def get_extractor(content_type: str) -> Extractor:
    base_type = (content_type or "").split(";")[0].strip().lower()
    if base_type in _PASSTHROUGH_TYPES:
        return PassthroughExtractor()
    return AzureDocIntelligenceExtractor()
