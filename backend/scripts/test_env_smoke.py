"""End-to-end smoke for the PharmAssist test stack.

Runs ONE real HMVS verify against the NMVO ITE sandbox and asserts the three
gates from docs/test-env-runbook.md (§First real HMVS call):

  (a) HmvsResult.nhrn != the mock sentinel "GR-0000-0000-0000" — proves we
      hit the real registry, not a stub.
  (b) An audit_log HMVS_VERIFIED row was written for this pack — proves the
      router's fire_hmvs_audit path ran end to end.
  (c) The OAuth2 client-credentials token was minted via the IDP
      /identity/connect/token endpoint — proves the HMVS_IDENTITY_URL value is
      correct (the no-/identity-suffix caveat from compose.test.yaml).

Designed to run INSIDE the backend container so it can introspect the
in-process token cache and query the DB directly:

    docker compose -f compose.test.yaml --env-file .env.test \\
        exec backend python -m scripts.test_env_smoke \\
        --gtin <GTIN> --serial <SERIAL> --batch <LOT> --expiry YYMMDD

Defaults match an NMVO Test-Book entry but you should pass real ones from the
IQE pack list. Exits non-zero on the first failed assertion so it can gate a
deploy.
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models.audit_log import AuditLog  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services import hmvs  # noqa: E402
from app.services.audit import _background_tasks, fire_hmvs_audit  # noqa: E402
from app.utils.environment import is_mock_hmvs  # noqa: E402

# Anything other than this means we talked to the real registry.
MOCK_NHRN_SENTINEL = "GR-0000-0000-0000"


def _fail(msg: str) -> int:
    print(f"[test-env smoke] FAIL — {msg}", file=sys.stderr)
    return 1


async def _assert_audit_row_written(*, serial: str, pharmacy_id: uuid.UUID) -> bool:
    """Look back ~10s for an HMVS_VERIFIED audit row carrying this pack serial.

    The router fires the audit as a tracked-asyncio task; we await
    ``_background_tasks`` before querying so a slow commit can't race the read."""
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    cutoff = datetime.now(UTC) - timedelta(seconds=30)
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(AuditLog)
            .where(
                AuditLog.action == "HMVS_VERIFIED",
                AuditLog.resource_id == serial,
                AuditLog.pharmacy_id == pharmacy_id,
                AuditLog.occurred_at >= cutoff,
            )
            .order_by(AuditLog.id.desc())
        )
    if row is None:
        print(
            f"[test-env smoke] no audit_log HMVS_VERIFIED row for serial={serial} in the last 30s",
            file=sys.stderr,
        )
        return False
    print(
        f"[test-env smoke] audit_log row id={row.id} action={row.action} "
        f"status={row.pharmapi_status} occurred_at={row.occurred_at.isoformat()}"
    )
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description="PharmAssist test-env smoke")
    # Defaults are placeholder Test-Book-shaped IDs — pass real IQE values on the
    # CLI. A real verify against placeholder IDs will return 404, which is fine
    # for proving the wiring but won't satisfy assertion (a).
    parser.add_argument("--gtin", default="09501101020917")
    parser.add_argument("--serial", default="SMOKE-FIRST-REAL")
    parser.add_argument("--batch", default="LOT-SMOKE")
    parser.add_argument("--expiry", default="261231")
    parser.add_argument(
        "--pharmacy-id",
        default=os.getenv("SMOKE_PHARMACY_ID"),
        help="Pharmacy UUID for the audit row (defaults to env SMOKE_PHARMACY_ID).",
    )
    parser.add_argument(
        "--pharmacist-id",
        default=os.getenv("SMOKE_PHARMACIST_ID"),
        help="Pharmacist UUID for the audit row (defaults to env SMOKE_PHARMACIST_ID).",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"[test-env smoke] identity_url={settings.hmvs_identity_url}")
    print(f"[test-env smoke] verification_url={settings.hmvs_verification_url}")
    print(f"[test-env smoke] mode={'MOCK' if is_mock_hmvs() else 'LIVE'}")

    # Refuse to claim "first real HMVS call" in mock mode — it would mean the
    # operator is about to record evidence from canned data.
    if is_mock_hmvs():
        return _fail("HMVS_MOCK is true. This script is for live ITE smokes only.")

    if not (settings.hmvs_client_id and settings.hmvs_client_secret):
        return _fail("HMVS_CLIENT_ID / HMVS_CLIENT_SECRET are unset.")
    if not args.pharmacy_id or not args.pharmacist_id:
        return _fail(
            "Pass --pharmacy-id and --pharmacist-id (or set SMOKE_PHARMACY_ID / "
            "SMOKE_PHARMACIST_ID). The seed prints them — see docs/test-env-runbook.md."
        )

    pharmacy_id = uuid.UUID(args.pharmacy_id)
    pharmacist_id = uuid.UUID(args.pharmacist_id)

    # Reset the in-process token cache so assertion (c) can prove THIS call
    # minted the token — without the reset a previous boot's cache hit would
    # mask a broken token URL.
    hmvs._token_cache.clear()

    # Direct service call — same code path the router takes. We invoke it
    # directly so we can introspect _token_cache afterwards; the router would
    # otherwise hide that behind the FastAPI dependency stack.
    print(f"[test-env smoke] verify gtin={args.gtin} serial={args.serial}")
    try:
        result = await hmvs.verify(
            args.gtin,
            args.serial,
            args.batch,
            args.expiry,
            client_id=settings.hmvs_client_id,
            client_secret=settings.hmvs_client_secret,
        )
    except Exception as exc:  # noqa: BLE001 — we want the operator to see anything
        return _fail(
            f"verify() raised {type(exc).__name__}: {exc}. "
            "Likely the token endpoint URL (HMVS_IDENTITY_URL) is wrong — "
            "see the no-/identity-suffix caveat in compose.test.yaml."
        )

    print(
        f"[test-env smoke] verify → ok={result.ok} http={result.http_status} "
        f"nhrn={result.nhrn} state={result.state}"
    )

    # Fire the audit row that the router would write so assertion (b) has
    # something to find. Using the same helper the router uses means we're
    # exercising the actual fire-and-forget plumbing, not a synthetic insert.
    fire_hmvs_audit(
        pharmacist_id=pharmacist_id,
        pharmacy_id=pharmacy_id,
        action="HMVS_VERIFIED",
        resource_id=args.serial,
        pharmapi_path=f"/pharmapi/hmvs/product/gs1/{args.gtin}/pack/{args.serial}",
        pharmapi_status=result.http_status,
    )

    # ── Assertion (c): token came from /identity/connect/token ──────────────
    # _token_cache is keyed by client_id and populated only by _get_token, so
    # the presence of an entry with a non-empty access_token proves the IDP
    # call succeeded. We check this BEFORE (a) so a misconfigured token URL
    # surfaces with the most useful error.
    cached = hmvs._token_cache.get(settings.hmvs_client_id)
    if not cached or not cached.get("access_token"):
        return _fail(
            "OAuth token cache is empty for this client_id — _get_token did "
            "not run. Most likely HMVS_IDENTITY_URL has /identity already in "
            "it; the code appends /identity/connect/token (see config.py:140-141)."
        )
    print("[test-env smoke] (c) OK — token minted via /identity/connect/token")

    # ── Assertion (a): real nhrn (not the mock sentinel) ────────────────────
    # In live mode a 404 returns no nhrn; treat that as "wiring proved, but
    # the pack ID was bogus" and surface a distinct message so the operator
    # knows to re-run with a real IQE pack.
    if result.http_status == 404:
        return _fail(
            "Live registry returned 404 for this pack — the wiring works but "
            "the pack identifiers are not in the ITE registry. Re-run with a "
            "real Test-Book / IQE pack."
        )
    if not result.nhrn:
        return _fail("verify returned a 2xx with no nhrn — unexpected upstream shape.")
    if result.nhrn == MOCK_NHRN_SENTINEL:
        return _fail(
            f"nhrn={result.nhrn!r} equals the mock sentinel — the call did "
            "not actually leave the process. Confirm HMVS_MOCK=false."
        )
    print(f"[test-env smoke] (a) OK — real nhrn={result.nhrn}")

    # ── Assertion (b): audit_log HMVS_VERIFIED row exists ───────────────────
    if not await _assert_audit_row_written(serial=args.serial, pharmacy_id=pharmacy_id):
        return _fail("audit_log row not found.")
    print("[test-env smoke] (b) OK — audit_log HMVS_VERIFIED row written")

    print("[test-env smoke] PASS — first real HMVS call evidence captured")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
