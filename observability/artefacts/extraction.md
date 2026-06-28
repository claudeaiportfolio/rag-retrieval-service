# Extraction live validation (Azure Document Intelligence)

Validated against the **real** provisioned ADI resource (2026-06-28), AAD-only
(no keys), with the committed `corpus/pdf/sample-policy.pdf` (3 pages, one
distinct fact per page).

## Result — page-accurate provenance, end to end

ADI (`prebuilt-layout`, Markdown output) extracted the PDF and returned real
per-page spans; the seam's offset→page mapping resolved every fact to its page:

| fact (text) | source page | `page_for_offset` |
|---|---|---|
| "…lookback period is 24 months…" | 1 | **1** ✓ |
| "…debt-to-income ratio… 45 percent…" | 2 | **2** ✓ |
| "…retained for 7 years…" | 3 | **3** ✓ |

Extracted 594 chars of Markdown; page spans `[(1, 0, 201), (2, 201, 217),
(3, 418, 176)]`. This exercises the new, risky surface live: **AAD auth via
workload identity, real extraction, and the provenance map** — exactly what the
in-cluster ingest path runs, which the unit tests cover deterministically
(`tests/unit/test_extraction.py`).

## Honest caveats

- **Clean digital PDF, not OCR.** The fixture is generated (text-layer), so this
  validates the extraction→provenance→citation path, not OCR fidelity on a
  scanned/messy document — that's ADI's job and would need a real scanned file.
- **In-pod ingest not run this round.** The full upload→worker→DB→retrieval path
  was blocked by **shared-cluster capacity** (regular nodes full, spot pool in
  scale-up backoff — an environment limit, not a code issue), so the ADI call was
  validated directly against the live endpoint instead. The pod wiring (worker
  routes on content_type, inserts page_start/page_end) is unit-tested.

## Reproduce

```bash
DOC_INTELLIGENCE_ENDPOINT="https://<adi>.cognitiveservices.azure.com/" \
  uv run python - <<'PY'
import asyncio
from common.extraction import AzureDocIntelligenceExtractor
doc = asyncio.run(AzureDocIntelligenceExtractor().extract(
    open("corpus/pdf/sample-policy.pdf","rb").read(), "application/pdf"))
print(len(doc.markdown), [(s.page, s.offset, s.length) for s in doc.pages])
PY
```
