"""Create or update a staff user (password + 4-digit PIN, both PBKDF2-hashed).

    python3 -m security.add_user --staff-id dr.smith --name "Dr. Sam Smith" --role surgeon

Prompts for password and PIN (not echoed). For scripted setup you may instead
set SECOND_LOOK_NEW_PASSWORD and SECOND_LOOK_NEW_PIN. Plaintext is never written.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from .auth import (DEFAULT_USERS_FILE, MIN_PASSWORD_LENGTH, PIN_LENGTH, hash_secret, is_valid_pin,
                   normalize_staff_id)


def _ask(prompt: str, env_var: str) -> str:
    value = os.environ.get(env_var)
    if value:
        return value
    first = getpass.getpass(prompt)
    if getpass.getpass("Repeat: ") != first:
        sys.exit("Entries do not match.")
    return first


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--staff-id", required=True)
    p.add_argument("--name", required=True, help="Display name, e.g. 'Dr. Dana Demo'")
    p.add_argument("--role", default="clinician")
    p.add_argument("--file", type=Path, default=DEFAULT_USERS_FILE)
    p.add_argument("--force", action="store_true", help="Replace an existing user with this staff ID")
    args = p.parse_args(argv)

    staff_id = normalize_staff_id(args.staff_id)
    if not staff_id or len(staff_id) > 64:
        sys.exit("Invalid staff ID.")

    data = {"users": []}
    if args.file.exists():
        data = json.loads(args.file.read_text(encoding="utf-8"))
    existing = [u for u in data.get("users", []) if normalize_staff_id(u.get("staff_id")) == staff_id]
    if existing and not args.force:
        sys.exit(f"User {staff_id!r} already exists (use --force to replace).")

    password = _ask("Password: ", "SECOND_LOOK_NEW_PASSWORD")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    pin = _ask(f"{PIN_LENGTH}-digit PIN: ", "SECOND_LOOK_NEW_PIN")
    if not is_valid_pin(pin):
        sys.exit(f"PIN must be exactly {PIN_LENGTH} digits.")

    record = {
        "staff_id": staff_id,
        "display_name": args.name,
        "role": args.role,
        "password_hash": hash_secret(password),
        "pin_hash": hash_secret(pin),
    }
    data["users"] = [u for u in data.get("users", []) if normalize_staff_id(u.get("staff_id")) != staff_id]
    data["users"].append(record)
    data["users"].sort(key=lambda u: u["staff_id"])
    args.file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {staff_id} ({args.role}) to {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
