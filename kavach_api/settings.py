"""Settings management for KAVACH API."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping


DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
DEFAULT_JWT_TTL_MINUTES = 480
DEFAULT_PBKDF2_ITERATIONS = 600000
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_FIR_CHARS = 5000
DEFAULT_MAX_CSV_ROWS = 500000
DEFAULT_LOGIN_FAIL_LIMIT = 5
DEFAULT_LOGIN_FAIL_WINDOW_SECONDS = 300

DISCLAIMER = (
    "Leads are decision support derived only from the uploaded records. "
    "They are not findings of guilt and not proof."
)


def repo_root() -> Path:
    """Return repository root path relative to this file."""
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Frozen application configuration settings."""
    runtime_dir: Path
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    jwt_ttl_minutes: int = DEFAULT_JWT_TTL_MINUTES
    pbkdf2_iterations: int = DEFAULT_PBKDF2_ITERATIONS
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_fir_chars: int = DEFAULT_MAX_FIR_CHARS
    max_csv_rows: int = DEFAULT_MAX_CSV_ROWS
    login_fail_limit: int = DEFAULT_LOGIN_FAIL_LIMIT
    login_fail_window_seconds: int = DEFAULT_LOGIN_FAIL_WINDOW_SECONDS


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """
    Load settings from environment mapping or os.environ.
    No import-time side effects.
    """
    if env is None:
        env = os.environ

    # 1. runtime_dir
    runtime_env = env.get("KAVACH_RUNTIME_DIR")
    if runtime_env:
        runtime_dir = Path(runtime_env).resolve()
    else:
        runtime_dir = (repo_root() / "runtime").resolve()

    # 2. cors_origins
    cors_env = env.get("KAVACH_CORS_ORIGINS")
    if cors_env:
        # Accept JSON array or comma-separated list
        stripped = cors_env.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                cors_origins = tuple(str(x).strip() for x in parsed if str(x).strip())
            except Exception:
                cors_origins = tuple(x.strip() for x in stripped[1:-1].split(",") if x.strip())
        else:
            cors_origins = tuple(x.strip() for x in cors_env.split(",") if x.strip())
    else:
        cors_origins = DEFAULT_CORS_ORIGINS

    # 3. jwt_ttl_minutes
    jwt_env = env.get("KAVACH_JWT_TTL_MIN")
    jwt_ttl_minutes = int(jwt_env) if jwt_env else DEFAULT_JWT_TTL_MINUTES

    # 4. pbkdf2_iterations
    pbkdf2_env = env.get("KAVACH_PBKDF2_ITERATIONS")
    pbkdf2_iterations = int(pbkdf2_env) if pbkdf2_env else DEFAULT_PBKDF2_ITERATIONS

    # 5. max_upload_bytes
    upload_env = env.get("KAVACH_MAX_UPLOAD_BYTES")
    max_upload_bytes = int(upload_env) if upload_env else DEFAULT_MAX_UPLOAD_BYTES

    return Settings(
        runtime_dir=runtime_dir,
        cors_origins=cors_origins,
        jwt_ttl_minutes=jwt_ttl_minutes,
        pbkdf2_iterations=pbkdf2_iterations,
        max_upload_bytes=max_upload_bytes,
        max_fir_chars=DEFAULT_MAX_FIR_CHARS,
        max_csv_rows=DEFAULT_MAX_CSV_ROWS,
        login_fail_limit=DEFAULT_LOGIN_FAIL_LIMIT,
        login_fail_window_seconds=DEFAULT_LOGIN_FAIL_WINDOW_SECONDS,
    )
