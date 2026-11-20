"""Command-line utility to create a user account in KAVACH UserStore."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Add repository root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kavach_api.security import UserStore, ROLES
from kavach_api.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a KAVACH user account.")
    parser.add_argument("--username", "-u", help="Username for the new account")
    parser.add_argument("--role", "-r", choices=ROLES, help="Role for the new account (viewer, analyst, admin)")
    args = parser.parse_args()

    username = args.username
    if not username:
        username = input("Username: ").strip()

    role = args.role
    if not role:
        role_input = input("Role (viewer, analyst, admin) [analyst]: ").strip()
        role = role_input or "analyst"

    if role not in ROLES:
        print(f"Error: Invalid role {role!r}. Allowed roles: {', '.join(ROLES)}")
        return 1

    pw1 = getpass.getpass("Password: ")
    if len(pw1) < 10:
        print("Error: Password must be at least 10 characters long.")
        return 1

    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("Error: Passwords do not match.")
        return 1

    settings = load_settings()
    user_store = UserStore(
        path=settings.runtime_dir / "auth" / "users.json",
        iterations=settings.pbkdf2_iterations,
    )

    try:
        user_store.create_user(username=username, password=pw1, role=role)
        print(f"User {username!r} with role {role!r} created successfully.")
        return 0
    except Exception as e:
        print(f"Error creating user: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
