"""Unit tests for kavach_api security module."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
import pytest

from kavach_api.security import (
    ROLES,
    TokenError,
    UserStore,
    LoginLimiter,
    hash_password,
    verify_password,
    create_token,
    decode_token,
    role_at_least,
    load_or_create_secret,
)


def test_password_round_trip_and_mismatch():
    """Password hashing verifies correctly, and wrong password returns False."""
    pwd = "CorrectHorseBatteryStaple123"
    h = hash_password(pwd, iterations=1000)

    assert verify_password(pwd, h) is True
    assert verify_password("WrongPassword!", h) is False
    assert verify_password("", h) is False
    assert verify_password(pwd, "invalid_hash_string") is False


def test_two_hashes_of_same_password_differ():
    """Different random salts ensure two hashes of the same password differ."""
    pwd = "SecurePassword10Chars!"
    h1 = hash_password(pwd, iterations=1000)
    h2 = hash_password(pwd, iterations=1000)
    assert h1 != h2
    assert verify_password(pwd, h1) is True
    assert verify_password(pwd, h2) is True


def test_token_round_trip():
    """Valid token encodes claims and decodes successfully."""
    secret = "test_signing_secret_key_123456789"
    token = create_token(secret, username="analyst_1", role="analyst", ttl_seconds=3600)
    claims = decode_token(secret, token)

    assert claims["sub"] == "analyst_1"
    assert claims["role"] == "analyst"
    assert claims["exp"] > claims["iat"]


def test_token_tampering_rejected():
    """Tampered payload, tampered signature, and wrong secret fail validation."""
    secret = "secret_a_12345678901234567890"
    other_secret = "secret_b_12345678901234567890"

    token = create_token(secret, username="user1", role="viewer", ttl_seconds=600)
    parts = token.split(".")

    # Tampered signature
    bad_sig_token = f"{parts[0]}.{parts[1]}.AAAA"
    with pytest.raises(TokenError, match="signature"):
        decode_token(secret, bad_sig_token)

    # Tampered payload (escalate role to admin)
    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    payload["role"] = "admin"
    bad_payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    tampered_token = f"{parts[0]}.{bad_payload_b64}.{parts[2]}"
    with pytest.raises(TokenError, match="signature"):
        decode_token(secret, tampered_token)

    # Token signed with another secret
    with pytest.raises(TokenError, match="signature"):
        decode_token(other_secret, token)


def test_token_alg_none_rejected():
    """Tokens with alg: none are explicitly rejected."""
    secret = "my_secret_key"
    header = {"alg": "none", "typ": "JWT"}
    payload = {"sub": "admin", "role": "admin", "iat": int(time.time()), "exp": int(time.time()) + 600}

    hdr_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    pay_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    none_token = f"{hdr_b64}.{pay_b64}."

    with pytest.raises(TokenError, match="Unsupported token algorithm"):
        decode_token(secret, none_token)


def test_token_expiration_rejected():
    """Expired tokens are rejected."""
    secret = "secret_exp_test"
    now = 1700000000.0
    token = create_token(secret, "user1", "viewer", ttl_seconds=60, now=now)

    # Before expiration
    assert decode_token(secret, token, now=now + 30)["sub"] == "user1"

    # Exactly expired / after expiration
    with pytest.raises(TokenError, match="expired"):
        decode_token(secret, token, now=now + 61)


def test_role_ordering():
    """Role hierarchy satisfies viewer < analyst < admin."""
    assert role_at_least("admin", "viewer") is True
    assert role_at_least("admin", "analyst") is True
    assert role_at_least("admin", "admin") is True

    assert role_at_least("analyst", "viewer") is True
    assert role_at_least("analyst", "analyst") is True
    assert role_at_least("analyst", "admin") is False

    assert role_at_least("viewer", "viewer") is True
    assert role_at_least("viewer", "analyst") is False
    assert role_at_least("viewer", "admin") is False

    with pytest.raises(ValueError):
        role_at_least("superuser", "admin")


def test_user_store_operations_and_security(tmp_path):
    """UserStore validates usernames, enforces password constraints, and never returns hashes."""
    users_file = tmp_path / "users.json"
    store = UserStore(users_file, iterations=1000)

    # Valid user creation
    u1 = store.create_user("rajesh_kumar", "ValidPassword123!", "analyst")
    assert u1 == {"username": "rajesh_kumar", "role": "analyst"}
    assert "password_hash" not in u1

    # Duplicate username (case-insensitive) rejected
    with pytest.raises(ValueError, match="already exists"):
        store.create_user("Rajesh_Kumar", "AnotherPassword99!", "viewer")

    # Invalid usernames rejected
    invalid_usernames = ["a", "ab", "user with space", "user@domain.com", "x" * 45]
    for un in invalid_usernames:
        with pytest.raises(ValueError, match="Invalid username format"):
            store.create_user(un, "ValidPassword123!", "viewer")

    # Password too short rejected
    with pytest.raises(ValueError, match="at least 10 characters"):
        store.create_user("new_user", "short9!", "viewer")

    # Authentication
    auth_ok = store.authenticate("rajesh_kumar", "ValidPassword123!")
    assert auth_ok == {"username": "rajesh_kumar", "role": "analyst"}

    auth_wrong_pw = store.authenticate("rajesh_kumar", "WrongPassword!")
    assert auth_wrong_pw is None

    auth_unknown_user = store.authenticate("unknown_user_99", "RandomPassword123!")
    assert auth_unknown_user is None

    # Get user
    got = store.get("rajesh_kumar")
    assert got == {"username": "rajesh_kumar", "role": "analyst"}
    assert "password_hash" not in got

    # List users
    store.create_user("amit_sharma", "SecondValidPassword123!", "viewer")
    users = store.list_users()
    assert len(users) == 2
    for u in users:
        assert "password_hash" not in u


def test_login_limiter_blocks_and_resets():
    """Limiter blocks after 5 failures and releases after sliding window."""
    fake_time = 1000.0

    def clock():
        return fake_time

    limiter = LoginLimiter(limit=5, window_seconds=300, clock=clock)

    # 4 failures -> not blocked
    for _ in range(4):
        limiter.record_failure("target_user")
    blocked, retry_after = limiter.is_blocked("target_user")
    assert blocked is False
    assert retry_after == 0

    # 5th failure -> blocked!
    limiter.record_failure("target_user")
    blocked, retry_after = limiter.is_blocked("target_user")
    assert blocked is True
    assert retry_after == 301  # window is 300 seconds

    # 6th failure -> still blocked
    limiter.record_failure("target_user")
    blocked, _ = limiter.is_blocked("target_user")
    assert blocked is True

    # Advance clock past window
    fake_time += 305.0
    blocked, retry_after = limiter.is_blocked("target_user")
    assert blocked is False
    assert retry_after == 0

    # Record success resets failures
    fake_time = 2000.0
    for _ in range(3):
        limiter.record_failure("user2")
    limiter.record_success("user2")
    # 2 more failures should not block because previous 3 were reset
    limiter.record_failure("user2")
    limiter.record_failure("user2")
    blocked, _ = limiter.is_blocked("user2")
    assert blocked is False


def test_load_or_create_secret(tmp_path):
    """Secret is created once and preserved across subsequent loads."""
    secret_file = tmp_path / "secret.key"
    s1 = load_or_create_secret(secret_file)
    assert len(s1) == 64
    assert secret_file.is_file()

    s2 = load_or_create_secret(secret_file)
    assert s1 == s2
