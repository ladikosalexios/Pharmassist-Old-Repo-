"""IQE probe: mint a client-credentials token and run one verify GET.

Reads everything from app.config / env — nothing hardcoded — so a future host
rotation (api-gr-iqe → api-gr → …) is one env var, no code change.

The probe deliberately overrides ``HMVS_MOCK=false`` before importing config so
it always exercises the live IQE path, even if the surrounding env left mock
on. This is the one place that bypass is correct — every other code path must
keep honouring ``HMVS_MOCK``.

Usage (inside the backend container, with HMVS_CLIENT_ID/SECRET in env):

    docker compose exec backend python -m scripts.hmvs_iqe_probe \\
        --gtin 09501101020917 --serial IQE-PROBE-0001 \\
        --batch LOT-IQE --expiry 261231
"""

from __future__ import annotations

import os

# Force live BEFORE app.config / app.services imports — get_settings() snapshots
# hmvs_mock at first call, and is_mock_hmvs() re-reads env per call, so both must
# see false from the start. Do this before any project import.
os.environ["HMVS_MOCK"] = "false"

import argparse  # noqa: E402
import asyncio  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import hmvs  # noqa: E402


async def main() -> int:
    p = argparse.ArgumentParser(description="HMVS IQE probe — token + one verify")
    p.add_argument("--gtin", default="09501101020917")
    p.add_argument("--serial", default="IQE-PROBE-0001")
    p.add_argument("--batch", default="LOT-IQE")
    p.add_argument("--expiry", default="261231")
    args = p.parse_args()

    settings = get_settings()
    if not (settings.hmvs_client_id and settings.hmvs_client_secret):
        print(
            "[IQE probe] ERROR: HMVS_CLIENT_ID/HMVS_CLIENT_SECRET unset.",
            file=sys.stderr,
        )
        return 2

    # Resolve the two URLs the way the runtime code does, so what we print is
    # what the verify/token calls will actually hit. No guessing.
    token_url = f"{settings.hmvs_identity_url}/identity/connect/token"
    verify_url = f"{settings.hmvs_verification_url}/product/gs1/{args.gtin}/pack/{args.serial}"

    print(f"[IQE probe] hmvs_identity_url      = {settings.hmvs_identity_url}")
    print(f"[IQE probe] hmvs_verification_url  = {settings.hmvs_verification_url}")
    print(f"[IQE probe] client_id              = {settings.hmvs_client_id}")
    print(f"[IQE probe] resolved token URL     = {token_url}")
    print(f"[IQE probe] resolved verify URL    = {verify_url}")

    # (a) Token mint
    print(f"[IQE probe] POST {token_url}")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            r = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.hmvs_client_id,
                    "client_secret": settings.hmvs_client_secret,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.ConnectError as exc:
        print(f"[IQE probe] DNS/connect FAILED: {exc!r}", file=sys.stderr)
        print(
            "[IQE probe] STOP — confirm the IQE host with Solidsoft (Filippidis).",
            file=sys.stderr,
        )
        return 3
    if r.status_code != 200:
        print(f"[IQE probe] token HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr)
        return 4
    payload = r.json()
    print(
        f"[IQE probe] token OK  expires_in={payload.get('expires_in')}s  "
        f"scope={payload.get('scope')!r}  token_type={payload.get('token_type')!r}"
    )

    # (b) One verify against the supplied pack
    result = await hmvs.verify(
        args.gtin,
        args.serial,
        args.batch,
        args.expiry,
        client_id=settings.hmvs_client_id,
        client_secret=settings.hmvs_client_secret,
    )
    print(
        f"[IQE probe] verify({args.gtin}/{args.serial}) → "
        f"http={result.http_status}  ok={result.ok}  state={result.state}  "
        f"operationCode={result.operation_code}"
    )
    print(f"[IQE probe] nhrn present? {result.nhrn is not None}  value={result.nhrn!r}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
