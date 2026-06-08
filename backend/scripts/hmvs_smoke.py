"""Smoke-test the HMVS (EU-FMD / ITE) integration end to end.

Fetches an OAuth2 client-credentials token from the ITE sandbox and verifies a
known test-book pack, printing the typed result. This is the manual gate for
sandbox env wiring — run it once after setting the ITE creds to confirm the
token host, base URLs and credentials all line up before touching the dispense
flow.

Usage (live ITE — needs HMVS_MOCK=false + HMVS_CLIENT_ID/SECRET in the env):

    HMVS_MOCK=false python -m scripts.hmvs_smoke \
        --gtin 09501101020917 --serial XYZ123 --batch LOT42 --expiry 261231

In mock mode (the default) it exercises the same code path against the canned
ITE-style responses — handy for proving the script wiring without the network.
The pack identifiers come from the Test Book (EMVS0710 V15.1); pass real ones
from the "Client credentials for the ITE" section for a live check.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings  # noqa: E402
from app.services import hmvs  # noqa: E402
from app.utils.environment import is_mock_hmvs  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="HMVS ITE smoke test")
    parser.add_argument("--gtin", default="09501101020917")
    parser.add_argument("--serial", default="SMOKE-0001")
    parser.add_argument("--batch", default="LOT-SMOKE")
    parser.add_argument("--expiry", default="261231")
    args = parser.parse_args()

    settings = get_settings()
    mode = "MOCK" if is_mock_hmvs() else "LIVE"
    print(f"[HMVS smoke] mode={mode}  identity={settings.hmvs_identity_url}")
    print(f"[HMVS smoke] verification={settings.hmvs_verification_url}")

    if not is_mock_hmvs() and not (settings.hmvs_client_id and settings.hmvs_client_secret):
        print(
            "[HMVS smoke] ERROR: HMVS_MOCK=false but HMVS_CLIENT_ID/HMVS_CLIENT_SECRET "
            "are unset. Set the ITE shared creds and retry.",
            file=sys.stderr,
        )
        return 2

    result = await hmvs.verify(
        args.gtin,
        args.serial,
        args.batch,
        args.expiry,
        client_id=settings.hmvs_client_id,
        client_secret=settings.hmvs_client_secret,
    )
    print(f"[HMVS smoke] verify({args.gtin}/{args.serial}) →")
    print(f"  ok={result.ok}  http={result.http_status}  state={result.state}")
    print(f"  operationCode={result.operation_code}  nhrn={result.nhrn}")
    print(f"  isIntermarket={result.is_intermarket}  alertId={result.alert_id}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
