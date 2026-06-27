"""Export the retrieval-api OpenAPI spec to docs/openapi.json (committed).

Imports the FastAPI app and dumps ``app.openapi()`` — no running server, DB, or
secrets needed (the lifespan isn't triggered on import). Keeping the published
contract in version control means consumers and PR diffs see API changes.

    uv run python scripts/export_openapi.py   # or: make openapi
"""

from __future__ import annotations

import json
import pathlib

from retrieval_api.main import app


def main() -> None:
    spec = app.openapi()
    out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    out.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"wrote {out} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
