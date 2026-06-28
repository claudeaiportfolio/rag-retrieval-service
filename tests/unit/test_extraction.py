"""Extraction seam tests — routing + the ADI result→ExtractedDoc parse +
offset→page provenance. No network (the live ADI API is paid + async)."""

from types import SimpleNamespace

from common.extraction import (
    AzureDocIntelligenceExtractor,
    PassthroughExtractor,
    get_extractor,
)
from common.extraction.azure_doc_intelligence import from_analyze_result
from common.extraction.base import ExtractedDoc, PageSpan


def _span(offset: int, length: int):
    return SimpleNamespace(offset=offset, length=length)


def _fake_adi_result():
    # Two pages: page 1 covers chars 0-19, page 2 covers 20-39.
    return SimpleNamespace(
        content="# Heading one\nbody one " + "x" * 17,  # len 40
        pages=[
            SimpleNamespace(page_number=1, spans=[_span(0, 20)]),
            SimpleNamespace(page_number=2, spans=[_span(20, 20)]),
        ],
    )


def test_router_passthrough_vs_adi():
    assert isinstance(get_extractor("text/markdown"), PassthroughExtractor)
    assert isinstance(get_extractor(""), PassthroughExtractor)
    assert isinstance(get_extractor("text/plain; charset=utf-8"), PassthroughExtractor)
    assert isinstance(get_extractor("application/pdf"), AzureDocIntelligenceExtractor)
    assert isinstance(
        get_extractor("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        AzureDocIntelligenceExtractor,
    )


async def test_passthrough_decodes_no_pages():
    doc = await PassthroughExtractor().extract(b"# Title\ntext", "text/markdown")
    assert doc.markdown == "# Title\ntext"
    assert doc.pages == []


def test_from_analyze_result_maps_pages():
    doc = from_analyze_result(_fake_adi_result())
    assert doc.markdown.startswith("# Heading one")
    assert [(s.page, s.offset, s.length) for s in doc.pages] == [(1, 0, 20), (2, 20, 20)]


def test_chunk_document_stamps_page_provenance():
    from common.chunking import chunk_document

    md = "# Section A\nAlpha content here.\n\n# Section B\nBeta content here."
    half = len(md) // 2
    pages = [PageSpan(1, 0, half), PageSpan(2, half, len(md) - half)]

    with_pages = chunk_document(document_id="d", tenant_id="t", source_doc="s", text=md, pages=pages)
    assert with_pages
    assert all(c.page_start in (1, 2) for c in with_pages)

    # Markdown/text with no provenance → None (cite by heading_path instead).
    no_pages = chunk_document(document_id="d", tenant_id="t", source_doc="s", text=md)
    assert all(c.page_start is None and c.page_end is None for c in no_pages)


def test_page_for_offset_and_range():
    doc = ExtractedDoc(
        markdown="x" * 40,
        pages=[PageSpan(1, 0, 20), PageSpan(2, 20, 20)],
    )
    assert doc.page_for_offset(0) == 1
    assert doc.page_for_offset(19) == 1
    assert doc.page_for_offset(20) == 2
    assert doc.page_for_offset(99) is None
    # a chunk spanning the page boundary reports first/last page
    assert doc.page_range(10, 30) == (1, 2)
    assert doc.page_range(0, 5) == (1, 1)
