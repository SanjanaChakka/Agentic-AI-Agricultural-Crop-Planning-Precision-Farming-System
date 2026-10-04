"""Regenerate the committed API contract artefacts.

Writes, from the repository root:

* ``api-contract.json`` - the full OpenAPI 3.1 schema;
* ``api-routes.txt`` - one route path per line, for quick diffing.

Run with::

    python scripts/generate_api_docs.py

Both files are checked in so that API changes show up as reviewable diffs. The
test suite does **not** regenerate them, so run this after changing any router or
Pydantic schema and commit the result alongside the code change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"

# The routers import application settings and build the ML registry, so the
# backend package has to be importable before the app object exists.
sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    """Write the contract and route listing. Returns a process exit code."""
    from app.main import app

    schema = app.openapi()

    contract_path = REPO_ROOT / "api-contract.json"
    contract_path.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    # Routes come from the OpenAPI paths, not ``app.routes``: the schema is the
    # published contract, and it normalises path converters such as
    # ``{doc_key:path}`` down to ``{doc_key}``. The framework's own docs routes
    # are excluded - this file records the application surface.
    routes = sorted(schema.get("paths", {}))
    routes_path = REPO_ROOT / "api-routes.txt"
    routes_path.write_text("\n".join(routes) + "\n", encoding="utf-8")

    operations = sum(
        1 for methods in schema.get("paths", {}).values() for method in methods if method in {"get", "post", "put", "patch", "delete"}
    )
    print(f"wrote {contract_path.name}: {len(schema.get('paths', {}))} paths, {operations} operations")
    print(f"wrote {routes_path.name}: {len(routes)} route paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())