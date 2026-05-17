"""Create a PharmAssist staff account (admin-portal user).

There is no UI to create the very first staff account — run this to bootstrap
one. Subsequent staff are managed in the admin UI. This is also the recovery
path if every staff account ends up deactivated.

Usage (from backend/):
    python scripts/create_staff.py --email you@pharmassist.gr --name "Your Name"
    # password is prompted, or set STAFF_PASSWORD in the environment

    python scripts/create_staff.py --email you@... --name "..." --reset-password
    # if the email already exists, overwrite its password instead of skipping
"""

import argparse
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models.staff_user import StaffUser  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

MIN_PASSWORD_LEN = 8


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a PharmAssist staff account.")
    parser.add_argument("--email", default=os.getenv("STAFF_EMAIL"))
    parser.add_argument("--name", default=os.getenv("STAFF_NAME"))
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="If the email already exists, overwrite its password instead of skipping.",
    )
    return parser.parse_args()


def _resolve_password() -> str:
    password = os.getenv("STAFF_PASSWORD")
    if not password and sys.stdin.isatty():
        password = getpass.getpass("Staff password: ")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise SystemExit(
            f"[create_staff] Password must be at least {MIN_PASSWORD_LEN} characters"
        )
    return password


async def create_staff(email: str, name: str, password: str, reset_password: bool) -> None:
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(StaffUser).where(StaffUser.email == email))
        if existing is not None:
            if not reset_password:
                print(
                    f"[create_staff] {email} already exists — skipping "
                    "(pass --reset-password to overwrite)"
                )
                return
            existing.password_hash = hashed
            existing.active = True
            await db.commit()
            print(f"[create_staff] ✓ password reset for {email} (id={existing.id})")
            return
        staff = StaffUser(email=email, full_name=name, password_hash=hashed, role="admin")
        db.add(staff)
        await db.commit()
        await db.refresh(staff)
        print(f"[create_staff] ✓ created staff account {email} (id={staff.id})")


def main() -> None:
    args = _parse_args()
    if not args.email or not args.name:
        raise SystemExit(
            "[create_staff] --email and --name are required (or STAFF_EMAIL / STAFF_NAME)"
        )
    password = _resolve_password()
    asyncio.run(create_staff(args.email, args.name, password, args.reset_password))


if __name__ == "__main__":
    main()
