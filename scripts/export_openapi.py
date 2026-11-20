"""Export OpenAPI JSON schema from KAVACH FastAPI application."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kavach_api.app import create_app


def export_openapi(dest_path: str | Path) -> None:
    """Export sorted-key OpenAPI JSON to destination path."""
    dest = Path(dest_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    app = create_app()
    openapi_schema = app.openapi()
    content = json.dumps(openapi_schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    dest.write_text(content, encoding="utf-8")
    print(f"Exported OpenAPI schema ({len(content)} bytes) to {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export KAVACH API OpenAPI JSON schema")
    parser.add_argument(
        "path",
        nargs="?",
        default="docs/api/openapi.json",
        help="Output path for openapi.json",
    )
    args = parser.parse_args()
    export_openapi(args.path)


if __name__ == "__main__":
    main()
