"""Document → chunks.

Two strategies, selectable via Settings.chunking_strategy:

- "fixed":   token-bounded sliding window with overlap, ignores structure.
- "heading": Markdown heading-aware. Splits on headings, preserves the
             heading_path (e.g. "Top / Subsection / Detail"), then sub-splits
             oversized sections with the fixed strategy. Better retrieval for
             docs that have structure.

When extraction provenance is supplied (`pages`: offset→page spans from the
Document Intelligence extractor), each chunk is stamped with the source page
range so the answer can cite a page. Page granularity is the *section* (the
right granularity for a citation — "page 14", not a character offset); a section
that spans pages yields page_start..page_end.
"""

from __future__ import annotations

import re

import tiktoken

from common.extraction.base import PageSpan
from common.models import Chunk

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_ENCODER = tiktoken.get_encoding("cl100k_base")


def _page_at(pages: list[PageSpan] | None, offset: int) -> int | None:
    for span in pages or []:
        if span.offset <= offset < span.offset + span.length:
            return span.page
    return None


def _page_range(
    pages: list[PageSpan] | None, start: int, end: int
) -> tuple[int | None, int | None]:
    if not pages:
        return None, None
    return _page_at(pages, start), _page_at(pages, max(start, end - 1))


def chunk_document(
    *,
    document_id: str,
    tenant_id: str,
    source_doc: str,
    text: str,
    pages: list[PageSpan] | None = None,
    strategy: str = "heading",
    chunk_size_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    if strategy == "heading":
        return _heading_chunks(
            document_id=document_id,
            tenant_id=tenant_id,
            source_doc=source_doc,
            text=text,
            pages=pages,
            chunk_size_tokens=chunk_size_tokens,
            overlap_tokens=overlap_tokens,
        )
    p_start, p_end = _page_range(pages, 0, len(text))
    return _fixed_chunks(
        document_id=document_id,
        tenant_id=tenant_id,
        source_doc=source_doc,
        heading_path="",
        text=text,
        start_index=0,
        page_start=p_start,
        page_end=p_end,
        chunk_size_tokens=chunk_size_tokens,
        overlap_tokens=overlap_tokens,
    )


def _heading_chunks(
    *,
    document_id: str,
    tenant_id: str,
    source_doc: str,
    text: str,
    pages: list[PageSpan] | None,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    sections = _split_by_heading(text)
    chunks: list[Chunk] = []
    for heading_path, body, body_start, body_end in sections:
        if not body.strip():
            continue
        p_start, p_end = _page_range(pages, body_start, body_end)
        token_count = len(_ENCODER.encode(body))
        if token_count <= chunk_size_tokens:
            chunks.append(
                Chunk(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    source_doc=source_doc,
                    heading_path=heading_path,
                    chunk_index=len(chunks),
                    token_count=token_count,
                    text=body.strip(),
                    page_start=p_start,
                    page_end=p_end,
                )
            )
        else:
            chunks.extend(
                _fixed_chunks(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    source_doc=source_doc,
                    heading_path=heading_path,
                    text=body,
                    start_index=len(chunks),
                    page_start=p_start,
                    page_end=p_end,
                    chunk_size_tokens=chunk_size_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
    return chunks


def _fixed_chunks(
    *,
    document_id: str,
    tenant_id: str,
    source_doc: str,
    heading_path: str,
    text: str,
    start_index: int,
    page_start: int | None = None,
    page_end: int | None = None,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    tokens = _ENCODER.encode(text)
    chunks: list[Chunk] = []
    step = max(1, chunk_size_tokens - overlap_tokens)
    for offset in range(0, len(tokens), step):
        window = tokens[offset : offset + chunk_size_tokens]
        if not window:
            break
        body = _ENCODER.decode(window).strip()
        if not body:
            continue
        chunks.append(
            Chunk(
                document_id=document_id,
                tenant_id=tenant_id,
                source_doc=source_doc,
                heading_path=heading_path,
                chunk_index=start_index + len(chunks),
                token_count=len(window),
                text=body,
                page_start=page_start,
                page_end=page_end,
            )
        )
    return chunks


def _split_by_heading(text: str) -> list[tuple[str, str, int, int]]:
    """Yield (heading_path, body, body_start, body_end). Preserves nesting via
    " / "; the offsets index into `text` (for page-provenance mapping)."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text, 0, len(text))]

    sections: list[tuple[str, str, int, int]] = []
    stack: list[str] = []

    if matches[0].start() > 0:
        leading = text[: matches[0].start()].strip()
        if leading:
            sections.append(("", leading, 0, matches[0].start()))

    for idx, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        stack = stack[: level - 1]
        stack.append(title)
        heading_path = " / ".join(stack)
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((heading_path, body, body_start, body_end))
    return sections
