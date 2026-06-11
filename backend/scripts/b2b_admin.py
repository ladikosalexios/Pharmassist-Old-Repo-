"""B2B tenant administration CLI — mint and revoke customers/locations/API keys.

Run inside the backend container (or from backend/ with the venv active):

    python -m scripts.b2b_admin create-customer --name "Chain SA" --email ops@chain.gr \
        [--tier core|clinical|platform]   # default core
    python -m scripts.b2b_admin set-tier --customer-id <uuid> --tier clinical
    python -m scripts.b2b_admin create-location --customer-id <uuid> --name "Store 12" \
        --pharmapi-unit-id 70466 --pharmapi-username chain12 [--eopyy] [--verify]
    python -m scripts.b2b_admin mint-key --location-id <uuid> --label "prod-pos"
    python -m scripts.b2b_admin rotate-key --key-id <uuid>   # mint sibling, revoke stays manual
    python -m scripts.b2b_admin revoke-key --key-id <uuid>
    python -m scripts.b2b_admin list
    python -m scripts.b2b_admin list-audit [--target-id <uuid>] [--limit N]

Every state-changing command appends one append-only row to b2b_admin_audit
(actor, action, target, before→after) in the SAME transaction as the change —
so no mutation lands without its audit row. Pass --actor to record an identity
other than the OS user; read the trail back with `list-audit`.

Security invariants:
  * The raw API key is printed EXACTLY ONCE at mint and stored only as a
    sha256 hash (services/api_keys.py). There is no recovery path — mint a
    new key instead. It is NEVER written to the audit trail.
  * The location's ΗΔΥΚΑ Pharmapi password is prompted via getpass when not
    supplied (avoid shell history), AES-256-GCM-encrypted at rest via
    app/crypto.py, and never printed, logged, or audited (nor is the username).
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
from app.db.models.b2b_admin_audit import B2bAdminAudit  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.routers.v1.deps import TIER_ORDER  # noqa: E402 — single source of the tier vocabulary
from app.services import b2b_admin_audit as audit  # noqa: E402
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402


def _default_env_label() -> str:
    """Follow the stack's MODE, not ENV (FT-13): keys only resolve where their
    prefix matches the deployment — pa_test_ on mock-mode (sandbox) stacks,
    pa_live_ on live-mode ones. Keying this on ENV minted dead pa_live_ keys
    on the ENV=production mock pilot box."""
    from app.services.api_keys import deployment_env_label

    return deployment_env_label()


async def create_customer(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        customer = Customer(name=args.name, contact_email=args.email, tier=args.tier, active=True)
        db.add(customer)
        await db.flush()  # assign customer.id for the audit target
        audit.add_admin_audit(
            db,
            actor=audit.resolve_actor(args.actor),
            action=audit.ACTION_CREATE_CUSTOMER,
            target_type=audit.TARGET_CUSTOMER,
            target_id=customer.id,
            details={"name": customer.name, "tier": customer.tier, "email": args.email},
        )
        await db.commit()
        await db.refresh(customer)
        print(
            f"[b2b-admin] customer created: id={customer.id} name={customer.name!r} "
            f"tier={customer.tier}"
        )


async def set_tier(args: argparse.Namespace) -> None:
    """Move a customer's entitlement tier (T2-1). Applies to the whole estate —
    per D-14 the tier lives on the customer, so every location + key under it
    gates on the new value immediately (the gate reads it per request)."""
    async with AsyncSessionLocal() as db:
        customer = await Customer.get_by_id(db, args.customer_id)
        if customer is None:
            sys.exit(f"[b2b-admin] customer {args.customer_id} not found")
        old = customer.tier
        if old == args.tier:
            # Idempotent no-op: don't write a phantom {"from": x, "to": x} audit
            # row or print a misleading "tier x -> x" line. Exit 0 so a script
            # that re-asserts a tier isn't treated as a failure.
            print(f"[b2b-admin] customer {customer.id} already on tier {old!r} — no change")
            return
        customer.tier = args.tier
        audit.add_admin_audit(
            db,
            actor=audit.resolve_actor(args.actor),
            action=audit.ACTION_SET_TIER,
            target_type=audit.TARGET_CUSTOMER,
            target_id=customer.id,
            details={"name": customer.name, "tier": {"from": old, "to": customer.tier}},
        )
        await db.commit()
        print(
            f"[b2b-admin] customer {customer.id} ({customer.name!r}) tier {old} -> {customer.tier}"
        )


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
        await db.flush()  # assign location.id for the audit target
        audit.add_admin_audit(
            db,
            actor=audit.resolve_actor(args.actor),
            action=audit.ACTION_CREATE_LOCATION,
            target_type=audit.TARGET_LOCATION,
            target_id=location.id,
            # NEVER the ΗΔΥΚΑ username/password — both are encrypted credentials.
            details={
                "customerId": str(customer.id),
                "name": location.name,
                "pharmapiUnitId": location.pharmapi_unit_id,
                "eopyy": location.is_eopyy,
            },
        )
        await db.commit()
        await db.refresh(location)
        print(
            f"[b2b-admin] location created: id={location.id} name={location.name!r} "
            f"unit={location.pharmapi_unit_id} eopyy={location.is_eopyy}"
        )


async def mint_key(args: argparse.Namespace) -> None:
    if args.env != _default_env_label():
        print(
            f"[b2b-admin] WARNING: this stack accepts pa_{_default_env_label()}_ keys only "
            f"(PHARMAPI_MOCK mode) — the pa_{args.env}_ key you are minting will NOT "
            "authenticate HERE. Only proceed if it is destined for the other environment."
        )
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
        await db.flush()  # assign key.id for the audit target
        audit.add_admin_audit(
            db,
            actor=audit.resolve_actor(args.actor),
            action=audit.ACTION_MINT_KEY,
            target_type=audit.TARGET_API_KEY,
            target_id=key.id,
            # NEVER the raw key — only its id/label/env. The key is shown once below.
            details={"locationId": str(location.id), "label": args.label, "env": args.env},
        )
        await db.commit()
        await db.refresh(key)
    print(f"[b2b-admin] API key minted for location {location.name!r} (key id {key.id})")
    print("[b2b-admin] This is the ONLY time the key is shown — store it now:")
    print(f"\n    {raw_key}\n")


async def rotate_key(args: argparse.Namespace) -> None:
    """Mint a SIBLING key on the same location and print BOTH ids (FT-9).

    Zero-downtime rotation: the old key stays active until you revoke it
    explicitly. Multiple active keys per location are supported (api_keys has
    no one-active-key constraint), so deploy the new key to the customer, watch
    its last_used_at move (`list`), THEN `revoke-key --key-id <old>`. Auto-
    revoking here would invite a lockout if the customer hasn't deployed yet."""
    async with AsyncSessionLocal() as db:
        old = await ApiKey.get_by_id(db, args.key_id)
        if old is None:
            sys.exit(f"[b2b-admin] api key {args.key_id} not found")
        if not old.active:
            print(f"[b2b-admin] NOTE: key {old.id} is already revoked — minting a sibling anyway")
        # The sibling must match THIS stack's mode to authenticate (FT-13), so
        # mint for the deployment env — the old key's env can't be recovered
        # from its stored hash anyway.
        raw_key = generate_api_key(_default_env_label())
        new = ApiKey(
            location_id=old.location_id,
            key_hash=hash_api_key(raw_key),
            label=args.label or (f"{old.label}-rotated" if old.label else "rotated"),
            active=True,
        )
        db.add(new)
        await db.flush()  # assign new.id for the audit target
        audit.add_admin_audit(
            db,
            actor=audit.resolve_actor(args.actor),
            action=audit.ACTION_ROTATE_KEY,
            target_type=audit.TARGET_API_KEY,
            target_id=new.id,
            details={
                "rotatedFrom": str(old.id),
                "locationId": str(old.location_id),
                "label": new.label,
            },
        )
        await db.commit()
        await db.refresh(new)
    print(f"[b2b-admin] rotated location key — old id {old.id} (still ACTIVE), new id {new.id}")
    print("[b2b-admin] Deploy the new key, confirm its last_used moves, THEN:")
    print(f"[b2b-admin]   python -m scripts.b2b_admin revoke-key --key-id {old.id}")
    print("[b2b-admin] This is the ONLY time the new key is shown — store it now:")
    print(f"\n    {raw_key}\n")


async def revoke_key(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        key = await ApiKey.get_by_id(db, args.key_id)
        if key is None:
            sys.exit(f"[b2b-admin] api key {args.key_id} not found")
        key.active = False
        audit.add_admin_audit(
            db,
            actor=audit.resolve_actor(args.actor),
            action=audit.ACTION_REVOKE_KEY,
            target_type=audit.TARGET_API_KEY,
            target_id=key.id,
            details={"locationId": str(key.location_id), "label": key.label},
        )
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
            print(f"customer {c.id}  {c.name}  tier={c.tier}{flag}")
            for loc in c.locations:
                flag = "" if loc.active else "  [INACTIVE]"
                print(
                    f"  location {loc.id}  {loc.name}  unit={loc.pharmapi_unit_id} "
                    f"eopyy={loc.is_eopyy}{flag}"
                )
                for k in loc.api_keys:
                    state = "active" if k.active else "revoked"
                    print(f"    key {k.id}  label={k.label!r}  {state}  last_used={k.last_used_at}")


async def list_audit(args: argparse.Namespace) -> None:
    """Print the operator audit trail, most recent first. --target-id narrows to
    one customer/location/key; --action narrows to one verb (e.g. SET_TIER);
    --limit bounds the rows."""
    async with AsyncSessionLocal() as db:
        # Filters first, then order+limit — reads in the order SQL applies them.
        stmt = select(B2bAdminAudit)
        if args.target_id is not None:
            stmt = stmt.where(B2bAdminAudit.target_id == str(args.target_id))
        if args.action is not None:
            stmt = stmt.where(B2bAdminAudit.action == args.action)
        stmt = stmt.order_by(B2bAdminAudit.occurred_at.desc()).limit(args.limit)
        rows = (await db.scalars(stmt)).all()
        if not rows:
            print("[b2b-admin] no audit entries")
            return
        for r in rows:
            target = f"{r.target_type or '-'}:{r.target_id or '-'}"
            print(
                f"{r.occurred_at:%Y-%m-%d %H:%M:%S%z}  {r.actor:>12}  "
                f"{r.action:<16} {target}  {r.details or {}}"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="b2b_admin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    # Shared by every state-changing command: who is recorded in the audit trail.
    # NOTE: --actor is SELF-DECLARED and unvalidated — the trail is an integrity
    # record (no mutation without a row), not proof of identity.
    actor_parent = argparse.ArgumentParser(add_help=False)
    actor_parent.add_argument(
        "--actor",
        default=None,
        help="Operator identity for the audit trail (default: OS user). "
        "Self-declared — records who claims to act, not a verified identity.",
    )

    p = sub.add_parser(
        "create-customer", parents=[actor_parent], help="Create a B2B customer (tenant root)"
    )
    p.add_argument("--name", required=True)
    p.add_argument("--email", default=None)
    p.add_argument(
        "--tier",
        default="core",
        choices=TIER_ORDER,
        help="Entitlement tier (default core); clinical/platform unlock Tier-2 /v1 routes",
    )
    p.set_defaults(func=create_customer)

    p = sub.add_parser(
        "set-tier",
        parents=[actor_parent],
        help="Change a customer's entitlement tier (whole estate)",
    )
    p.add_argument("--customer-id", required=True, type=uuid.UUID)
    p.add_argument("--tier", required=True, choices=TIER_ORDER)
    p.set_defaults(func=set_tier)

    p = sub.add_parser(
        "create-location",
        parents=[actor_parent],
        help="Create a billable location under a customer",
    )
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

    p = sub.add_parser(
        "mint-key", parents=[actor_parent], help="Mint an API key (plaintext shown once)"
    )
    p.add_argument("--location-id", required=True, type=uuid.UUID)
    p.add_argument("--label", default=None)
    p.add_argument("--env", default=_default_env_label(), choices=("live", "test"))
    p.set_defaults(func=mint_key)

    p = sub.add_parser(
        "rotate-key",
        parents=[actor_parent],
        help="Mint a sibling key for zero-downtime rotation (revoke stays manual)",
    )
    p.add_argument("--key-id", required=True, type=uuid.UUID, help="The key being rotated out")
    p.add_argument("--label", default=None, help="Label for the new key (default: <old>-rotated)")
    p.set_defaults(func=rotate_key)

    p = sub.add_parser("revoke-key", parents=[actor_parent], help="Revoke an API key")
    p.add_argument("--key-id", required=True, type=uuid.UUID)
    p.set_defaults(func=revoke_key)

    p = sub.add_parser("list", help="List customers → locations → keys")
    p.set_defaults(func=list_tenants)

    p = sub.add_parser("list-audit", help="Show the operator audit trail (most recent first)")
    p.add_argument(
        "--target-id", default=None, type=uuid.UUID, help="Filter to one customer/location/key id"
    )
    p.add_argument(
        "--action", default=None, choices=audit.ALL_ACTIONS, help="Filter to one action verb"
    )
    p.add_argument("--limit", default=20, type=int, help="Max rows to show (default 20)")
    p.set_defaults(func=list_audit)

    return parser


if __name__ == "__main__":
    cli_args = _build_parser().parse_args()
    asyncio.run(cli_args.func(cli_args))
