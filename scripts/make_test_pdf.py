"""Generate the controlled extraction-test PDF (corpus/pdf/sample-policy.pdf).

A regulated-style stand-in with a *distinct fact per page*, so the live e2e can
assert that an answer cites the right page (provenance), not just that retrieval
works. Content is ours → redistributable, version-pinned with the repo.

    uv run python scripts/make_test_pdf.py
"""

from __future__ import annotations

import pathlib

from fpdf import FPDF

# (heading, distinctive fact) per page — each fact only appears on its page.
PAGES = [
    (
        "Adverse credit",
        "The adverse-credit lookback period is 24 months from the application date. "
        "Applicants with a default registered within this window are referred to manual review.",
    ),
    (
        "Affordability assessment",
        "The maximum permitted debt-to-income ratio for unsecured lending is 45 percent. "
        "Stress testing applies a 3 percentage point rate increase to all variable commitments.",
    ),
    (
        "Document retention",
        "Lending decision records are retained for 7 years after account closure. "
        "Customer identity evidence is retained for 6 years under the firm's KYC policy.",
    ),
]


def main() -> None:
    pdf = FPDF()
    pdf.set_title("Consumer Lending Policy (sample)")
    for heading, body in PAGES:
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=16)
        pdf.multi_cell(0, 10, heading)
        pdf.ln(4)
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, body)

    out = pathlib.Path(__file__).resolve().parents[1] / "corpus" / "pdf" / "sample-policy.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    print(f"wrote {out} ({len(PAGES)} pages)")


if __name__ == "__main__":
    main()
