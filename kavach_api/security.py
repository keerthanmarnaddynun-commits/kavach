"""Security primitives: password hashing, tokens, roles, users and limiter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from typing import Any, Mapping

ROLES = ("viewer", "analyst", "admin")
ROLE_LEVELS: dict[str, int] = {
    "viewer": 1,
    "analyst": 2,
    "admin": 3,
}

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,40}\Z")


class TokenError(Exception):
    """Raised when token validation or decoding fails."""


class UserStoreCorrupt(Exception):
    """Raised when users.json exists but is unreadable or not a valid JSON object."""


def role_at_least(role: str, minimum: str) -> bool:
    """Return True if role has at least the privilege level of minimum."""
    if role not in ROLE_LEVELS:
        raise ValueError(f"Unknown role: {role!r}")
    if minimum not in ROLE_LEVELS:
        raise ValueError(f"Unknown minimum role: {minimum!r}")
    return ROLE_LEVELS[role] >= ROLE_LEVELS[minimum]


def hash_password(password: str, iterations: int) -> str:
    """Hash password with PBKDF2-HMAC-SHA256 and a random 16-byte salt."""
    salt = secrets.token_bytes(16)
    pw_bytes = password.encode("utf-8")
    derived = hashlib.pbkdf2_hmac("sha256", pw_bytes, salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    if not isinstance(stored, str):
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = parts[3]
    except Exception:
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived.hex(), expected_hash)


def _b64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Base64url decode with padding restoration."""
    pad_len = (-len(s)) % 4
    padded = s + ("=" * pad_len)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def create_token(
    secret: str | bytes,
    username: str,
    role: str,
    ttl_seconds: int,
    now: float | None = None,
) -> str:
    """Create a signed HS256 JWT token with standard claims."""
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role!r}")

    current_time = int(time.time() if now is None else now)
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "iat": current_time,
        "exp": current_time + int(ttl_seconds),
    }

    hdr_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{hdr_b64}.{payload_b64}".encode("ascii")

    sig = hmac.new(secret_bytes, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{hdr_b64}.{payload_b64}.{sig_b64}"


def decode_token(
    secret: str | bytes,
    token: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Decode and validate an HS256 JWT token."""
    if not isinstance(token, str):
        raise TokenError("Token must be a string")

    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError(f"Malformed token: expected 3 parts, got {len(parts)}")

    hdr_b64, payload_b64, sig_b64 = parts
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret

    # 1. Decode header
    try:
        hdr_bytes = _b64url_decode(hdr_b64)
        header = json.loads(hdr_bytes.decode("utf-8"))
    except Exception as e:
        raise TokenError(f"Invalid token header: {e}") from e

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise TokenError(f"Unsupported token algorithm: {header.get('alg')!r}")

    # 2. Verify signature
    signing_input = f"{hdr_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret_bytes, signing_input, hashlib.sha256).digest()
    expected_sig_b64 = _b64url_encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise TokenError("Token signature verification failed")

    # 3. Decode payload
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise TokenError(f"Invalid token payload: {e}") from e

    if not isinstance(payload, dict):
        raise TokenError("Token payload must be a JSON object")

    # 4. Check required claims
    for claim in ("sub", "role", "iat", "exp"):
        if claim not in payload:
            raise TokenError(f"Token missing required claim: {claim}")

    if payload["role"] not in ROLES:
        raise TokenError(f"Token contains invalid role: {payload['role']!r}")

    # 5. Check expiration
    current_time = int(time.time() if now is None else now)
    if current_time > payload["exp"]:
        raise TokenError(f"Token has expired (exp: {payload['exp']}, now: {current_time})")

    return payload


class UserStore:
    """Atomic JSON storage for user accounts and password hashes."""

    def __init__(self, path: str | Path, iterations: int = 600000):
        self.path = Path(path).resolve()
        self.iterations = iterations
        self._lock = threading.Lock()

    def _load_data(self) -> dict[str, dict[str, Any]]:
        """Load user records mapping lowercase username to record."""
        if not self.path.exists():
            return {}
        try:
            content = self.path.read_text(encoding="utf-8")
        except Exception as exc:
            raise UserStoreCorrupt(f"Cannot read users store file: {exc}") from exc

        if not content.strip():
            return {}

        try:
            data = json.loads(content)
        except Exception as exc:
            raise UserStoreCorrupt(f"Users store file contains invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise UserStoreCorrupt("Users store file is not a JSON object")
        return data

    def _save_data(self, data: dict[str, dict[str, Any]]) -> None:
        """Atomically write user records."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp_{secrets.token_hex(4)}")
        try:
            content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            temp_path.write_text(content, encoding="utf-8")
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def create_user(self, username: str, password: str, role: str) -> dict[str, Any]:
        """Create a new user. Rejects invalid names, weak passwords, and duplicates."""
        if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
            raise ValueError(f"Invalid username format: {username!r}")

        if not isinstance(password, str) or len(password) < 10:
            raise ValueError("Password must be at least 10 characters")

        if role not in ROLES:
            raise ValueError(f"Invalid role: {role!r}")

        key = username.lower()
        with self._lock:
            data = self._load_data()
            if key in data:
                raise ValueError(f"Username already exists: {username}")

            pw_hash = hash_password(password, self.iterations)
            record = {
                "username": username,
                "role": role,
                "password_hash": pw_hash,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            data[key] = record
            self._save_data(data)

        # Never return password hash
        return {"username": username, "role": role}

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        """
        Authenticate username and password.
        Spends similar time for unknown users by hashing a dummy password.
        """
        key = username.lower()
        with self._lock:
            data = self._load_data()
            user = data.get(key)

        if user is None:
            # Constant-time mitigation against user enumeration
            hash_password(password, self.iterations)
            return None

        if verify_password(password, user["password_hash"]):
            return {"username": user["username"], "role": user["role"]}
        return None

    def get(self, username: str) -> dict[str, Any] | None:
        """Return user info by username (never returns password hash)."""
        key = username.lower()
        with self._lock:
            data = self._load_data()
            user = data.get(key)

        if user is None:
            return None
        return {"username": user["username"], "role": user["role"]}

    def list_users(self) -> list[dict[str, Any]]:
        """List all users (never returns password hashes)."""
        with self._lock:
            data = self._load_data()
            users = [
                {"username": u["username"], "role": u["role"]}
                for u in sorted(data.values(), key=lambda x: x["username"].lower())
            ]
        return users


class LoginLimiter:
    """In-memory rate limiter for login failures with sliding window."""

    def __init__(
        self,
        limit: int = 5,
        window_seconds: int = 300,
        clock: Any = None,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock if clock is not None else time.time
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def record_failure(self, username: str) -> None:
        """Record a login failure timestamp for username."""
        key = username.lower()
        now = float(self._clock())
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._failures.setdefault(key, [])
            timestamps.append(now)
            # Prune old entries
            self._failures[key] = [t for t in timestamps if t > cutoff]

    def is_blocked(self, username: str) -> tuple[bool, int]:
        """
        Check if user is blocked.
        Returns (is_blocked, retry_after_seconds).
        """
        key = username.lower()
        now = float(self._clock())
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._failures.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._failures[key] = valid_timestamps

            if len(valid_timestamps) >= self.limit:
                oldest_in_window = valid_timestamps[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now) + 1)
                return True, retry_after
            return False, 0

    def record_success(self, username: str) -> None:
        """Clear recorded failures upon successful login."""
        key = username.lower()
        with self._lock:
            self._failures.pop(key, None)


def load_or_create_secret(path: str | Path) -> str:
    """Load signing secret from path or create 32 random bytes hex."""
    target = Path(path).resolve()
    if target.is_file():
        return target.read_text(encoding="utf-8").strip()

    target.parent.mkdir(parents=True, exist_ok=True)
    secret_hex = secrets.token_hex(32)

    temp_path = target.with_suffix(f"{target.suffix}.tmp_{secrets.token_hex(4)}")
    try:
        temp_path.write_text(secret_hex + "\n", encoding="utf-8")
        # Restrict permissions best effort
        try:
            temp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return secret_hex
