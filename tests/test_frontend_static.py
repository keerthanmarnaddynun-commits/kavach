"""Frontend static design lint and package manifest verification (Step C1)."""
from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
SRC_DIR = WEB_DIR / "src"

def get_banned_words() -> list[str]:
    steps_file = REPO_ROOT / "docs" / "runbook" / "chunk_C.steps.json"
    data = json.loads(steps_file.read_text(encoding="utf-8"))
    banned_all = data.get("global", {}).get("banned_all", [])
    extra_words = ["kingpin", "guilty", "arrest", "ai-powered"]
    return banned_all + extra_words

FORBIDDEN_PATTERNS = [
    "gradient(",
    "backdrop-filter",
    "box-shadow",
    "dangerouslySetInnerHTML",
    "innerHTML",
    "eval(",
    "document.write",
    "localStorage",
]

ALLOWED_URL_HOSTS = ["127.0.0.1", "localhost", "www.w3.org"]


def is_emoji(char: str) -> bool:
    cp = ord(char)
    return (
        0x1F600 <= cp <= 0x1F64F
        or 0x1F300 <= cp <= 0x1F5FF
        or 0x1F680 <= cp <= 0x1F6FF
        or 0x1F1E0 <= cp <= 0x1F1FF
        or 0x2600 <= cp <= 0x26FF
        or 0x2700 <= cp <= 0x27BF
        or 0x1F900 <= cp <= 0x1FAFF
    )


def get_frontend_files() -> list[Path]:
    files = [WEB_DIR / "index.html"]
    for p in SRC_DIR.rglob("*"):
        if p.is_file():
            # Exclude fixtures directory
            rel = p.relative_to(SRC_DIR).as_posix()
            if rel.startswith("fixtures/"):
                continue
            if p.suffix in (".js", ".jsx", ".html", ".css"):
                files.append(p)
    return files


def test_package_json_manifest():
    """Verify package.json contains exact pinned versions and only required packages."""
    pkg_file = WEB_DIR / "package.json"
    assert pkg_file.is_file(), "package.json missing in web/"

    data = json.loads(pkg_file.read_text(encoding="utf-8"))
    assert data.get("private") is True
    assert data.get("type") == "module"

    expected_deps = {
        "react": "18.3.1",
        "react-dom": "18.3.1",
        "cytoscape": "3.30.2",
        "cytoscape-fcose": "2.2.0",
    }
    expected_dev = {
        "vite": "5.4.11",
        "@vitejs/plugin-react": "4.3.4",
        "vitest": "2.1.8",
    }

    assert data.get("dependencies") == expected_deps
    assert data.get("devDependencies") == expected_dev

    all_versions = list(data.get("dependencies", {}).values()) + list(data.get("devDependencies", {}).values())
    for v in all_versions:
        assert not any(c in v for c in ("^", "~", "*")), f"Version {v} contains non-pinned character"


def test_design_lint_frontend_files():
    """Verify web files follow static design constraints and offline rules."""
    files = get_frontend_files()
    assert len(files) > 0, "No frontend source files found"

    url_regex = re.compile(r"https?://([a-zA-Z0-9.-]+)")

    violations = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        text_lower = text.lower()

        # Check banned words
        banned_words = get_banned_words()
        for bw in banned_words:
            # Word boundary check for word tokens
            pattern = rf"\b{re.escape(bw)}\b"
            if re.search(pattern, text_lower):
                violations.append(f"{f.name}: contains banned word {bw!r}")

        # Check forbidden CSS/JS patterns
        for fp in FORBIDDEN_PATTERNS:
            if fp.lower() in text_lower:
                violations.append(f"{f.name}: contains forbidden pattern {fp!r}")

        # Check emoji characters
        for char in text:
            if is_emoji(char):
                violations.append(f"{f.name}: contains emoji character {char!r}")
                break

        # Check URLs (offline rule: only 127.0.0.1, localhost, www.w3.org)
        for match in url_regex.finditer(text):
            host = match.group(1).lower()
            if not any(host == allowed or host.startswith(f"{allowed}:") for allowed in ALLOWED_URL_HOSTS):
                violations.append(f"{f.name}: contains unauthorized external URL host {host!r}")

    assert not violations, f"Design lint violations:\n" + "\n".join(violations)
