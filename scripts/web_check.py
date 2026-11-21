"""Runner for web build, tests, and dist size check."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
MAX_SIZE_BYTES = 3 * 1024 * 1024  # 3 MB


def get_npm() -> str:
    npm_path = shutil.which("npm")
    if not npm_path:
        print("ERROR: npm not found in PATH")
        sys.exit(1)
    return npm_path


def run_build() -> int:
    npm = get_npm()
    res = subprocess.run(
        [npm, "run", "build"],
        cwd=str(WEB_DIR),
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        print("BUILD OK")
        return 0
    lines = (res.stdout + "\n" + res.stderr).splitlines()
    print("\n".join(lines[-40:]))
    return res.returncode or 1


def run_test() -> int:
    npm = get_npm()
    res = subprocess.run(
        [npm, "test"],
        cwd=str(WEB_DIR),
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        print("TESTS OK")
        return 0
    lines = (res.stdout + "\n" + res.stderr).splitlines()
    print("\n".join(lines[-40:]))
    return res.returncode or 1


def run_size() -> int:
    if not DIST_DIR.exists():
        print("ERROR: dist directory does not exist. Run build first.")
        return 1
    total_size = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file())
    if total_size < MAX_SIZE_BYTES:
        print("SIZE OK")
        return 0
    print(f"ERROR: dist size {total_size} exceeds 3 MB limit")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Web check runner")
    parser.add_argument("command", choices=["build", "test", "size"])
    args = parser.parse_args()

    if args.command == "build":
        sys.exit(run_build())
    elif args.command == "test":
        sys.exit(run_test())
    elif args.command == "size":
        sys.exit(run_size())


if __name__ == "__main__":
    main()
