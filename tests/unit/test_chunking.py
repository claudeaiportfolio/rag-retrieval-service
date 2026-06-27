from common.chunking import chunk_document


def test_heading_chunks_preserve_heading_path():
    text = """\
# Top

intro paragraph.

## Sub A

content A.

## Sub B

content B.
"""
    chunks = chunk_document(
        document_id="d1",
        tenant_id="t1",
        source_doc="doc.md",
        text=text,
        strategy="heading",
        chunk_size_tokens=512,
        overlap_tokens=32,
    )
    paths = [c.heading_path for c in chunks]
    assert "Top" in paths
    assert "Top / Sub A" in paths
    assert "Top / Sub B" in paths
    assert all(c.text for c in chunks)


def test_fixed_strategy_respects_overlap():
    text = "word " * 2000
    chunks = chunk_document(
        document_id="d1",
        tenant_id="t1",
        source_doc="doc.md",
        text=text,
        strategy="fixed",
        chunk_size_tokens=128,
        overlap_tokens=16,
    )
    assert len(chunks) > 1
    assert all(c.token_count <= 128 for c in chunks)
    assert chunks[0].chunk_index == 0
    assert chunks[-1].chunk_index == len(chunks) - 1


def test_oversized_heading_section_is_split():
    body = "alpha " * 1000
    text = f"# Big\n\n{body}\n"
    chunks = chunk_document(
        document_id="d1",
        tenant_id="t1",
        source_doc="doc.md",
        text=text,
        strategy="heading",
        chunk_size_tokens=128,
        overlap_tokens=16,
    )
    big_chunks = [c for c in chunks if c.heading_path == "Big"]
    assert len(big_chunks) > 1
