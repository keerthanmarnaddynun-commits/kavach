"""Programmatic uvicorn server runner for KAVACH API."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run uvicorn server serving KAVACH API."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    import uvicorn
    from kavach_api.app import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KAVACH API uvicorn server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number (default: 8000)",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
