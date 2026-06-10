"""B2B tenant administration CLI — mint and revoke customers/locations/API keys.

Run inside the backend container (or from backend/ with the venv active):

    python -m scripts.b2b_admin create-customer --name "Chain SA" --email ops@chain.gr
    python -m scripts.b2b_admin create-location --customer-id <uuid> --name "Store 12" \
        --pharmapi-unit-id 70466 --pharmapi-username chain12 [--eopyy] [--verify]
    python -m scripts.b2b_admin mint-key --location-id <uuid> --label "prod-pos"
    python -m scripts.b2b_admin revoke-key --key-id <uuid>
    python -m scripts.b2b_admin list

Security invariants:
  * The raw API key is printed EXACTLY ONCE at mint and stored only as a
    sha256 hash (services/api_keys.py). There is no recovery path — mint a
    new key instead.
  * The location's ΗΔΥΚΑ Pharmapi password is prompted via getpass when not
    supplied (avoid shell history), AES-256-GCM-encrypted at rest via
    app/crypto.py, and never printed or logged.
"""

import argparse
import asyncio
import getpass
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.crypto import encrypt_credential  # noqa: E402
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402


def _default_env_label() -> str:
    env = os.getenv("ENV", "production")
    return "live" if env == "production" else "test"


async def create_customer(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        customer = Customer(name=args.name, contact_email=args.email, active=True)
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        print(f"[b2b-admin] customer created: id={customer.id} name={customer.name!r}")


async def create_location(args: argparse.Namespace) -> None:
    password = args.pharmapi_password or getpass.getpass("ΗΔΥΚΑ Pharmapi password: ")
    if not password:
        sys.exit("[b2b-admin] a Pharmapi password is required")

    if args.verify:
        from app.services.pharmapi import verify_pharmapi_credentials

        print(f"[b2b-admin] verifying {args.pharmapi_username!r} against ΗΔΥΚΑ ...")
        profile = await verify_pharmapi_credentials(args.pharmapi_username, password)
        units = profile.get("units") or []
        unit_ids = [u.get("id") for u in units]
        if args.pharmapi_unit_id not in unit_ids:
            print(
                f"[b2b-admin] WARNING: unit id {args.pharmapi_unit_id} not in the "
                f"account's units {unit_ids} — double-check before going live"
            )
        else:
            print("[b2b-admin] credentials OK, unit id matches")

    async with AsyncSessionLocal() as db:
        customer = await Customer.get_by_id(db, args.customer_id)
        if customer is None:
            sys.exit(f"[b2b-admin] customer {args.customer_id} not found")
        location = Location(
            customer_id=customer.id,
            name=args.name,
            address=args.address,
            pharmapi_unit_id=args.pharmapi_unit_id,
            pharmapi_username=encrypt_credential(args.pharmapi_username),
            pharmapi_password=encrypt_credential(password),
            is_eopyy=args.eopyy,
            active=True,
        )
        db.add(location)
        await db.commit()
        await db.refresh(location)
        print(
            f"[b2b-admin] location created: id={location.id} name={location.name!r} "
            f"unit={location.pharmapi_unit_id} eopyy={location.is_eopyy}"
        )


async def mint_key(args: argparse.Namespace) -> None:
    raw_key = generate_api_key(args.env)
    async with AsyncSessionLocal() as db:
        location = await Location.get_by_id(db, args.location_id)
        if location is None:
            sys.exit(f"[b2b-admin] location {args.location_id} not found")
        key = ApiKey(
            location_id=location.id,
            key_hash=hash_api_key(raw_key),
            label=args.label,
            active=True,
        )
        db.add(key)
        await db.commit()
        await db.refresh(key)
    print(f"[b2b-admin] API key minted for location {location.name!r} (key id {key.id})")
    print("[b2b-admin] This is the ONLY time the key is shown — store it now:")
    print(f"\n    {raw_key}\n")


async def revoke_key(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        key = await ApiKey.get_by_id(db, args.key_id)
        if key is None:
            sys.exit(f"[b2b-admin] api key {args.key_id} not found")
        key.active = False
        await db.commit()
        print(f"[b2b-admin] key {key.id} revoked (label={key.label!r})")


async def list_tenants(_args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        customers = (
            (
                await db.scalars(
                    select(Customer)
                    .options(joinedload(Customer.locations).joinedload(Location.api_keys))
                    .order_by(Customer.created_at)
                )
            )
            .unique()
            .all()
        )
        if not customers:
            print("[b2b-admin] no customers yet")
            return
        for c in customers:
            flag = "" if c.active else "  [INACTIVE]"
            print(f"customer {c.id}  {c.name}{flag}")
            for loc in c.locations:
                flag = "" if loc.active else "  [INACTIVE]"
                print(
                    f"  location {loc.id}  {loc.name}  unit={loc.pharmapi_unit_id} "
                    f"eopyy={loc.is_eopyy}{flag}"
                )
                for k in loc.api_keys:
                    state = "active" if k.active else "revoked"
                    print(f"    key {k.id}  label={k.label!r}  {state}  last_used={k.last_used_at}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="b2b_admin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-customer", help="Create a B2B customer (tenant root)")
    p.add_argument("--name", required=True)
    p.add_argument("--email", default=None)
    p.set_defaults(func=create_customer)

    p = sub.add_parser("create-location", help="Create a billable location under a customer")
    p.add_argument("--customer-id", required=True, type=uuid.UUID)
    p.add_argument("--name", required=True)
    p.add_argument("--address", default=None)
    p.add_argument("--pharmapi-unit-id", required=True, type=int, help="ΗΔΥΚΑ pharmacy unit id")
    p.add_argument("--pharmapi-username", required=True, help="Location's ΗΔΥΚΑ Basic-Auth user")
    p.add_argument(
        "--pharmapi-password",
        default=None,
        help="Location's ΗΔΥΚΑ password (omit to be prompted — avoids shell history)",
    )
    p.add_argument(
        "--eopyy", action="store_true", help="ΕΟΠΥΥ/isIka account (enables intolerances+history)"
    )
    p.add_argument(
        "--verify", action="store_true", help="Validate the creds against ΗΔΥΚΑ before saving"
    )
    p.set_defaults(func=create_location)

    p = sub.add_parser("mint-key", help="Mint an API key (plaintext shown once)")
    p.add_argument("--location-id", required=True, type=uuid.UUID)
    p.add_argument("--label", default=None)
    p.add_argument("--env", default=_default_env_label(), choices=("live", "test"))
    p.set_defaults(func=mint_key)

    p = sub.add_parser("revoke-key", help="Revoke an API key")
    p.add_argument("--key-id", required=True, type=uuid.UUID)
    p.set_defaults(func=revoke_key)

    p = sub.add_parser("list", help="List customers → locations → keys")
    p.set_defaults(func=list_tenants)

    return parser


if __name__ == "__main__":
    cli_args = _build_parser().parse_args()
    asyncio.run(cli_args.func(cli_args))
