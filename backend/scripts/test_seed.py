"""Diagnostic for the seed script — manual / interactive use.

Walks through what seed.py does, step by step, with verbose output so you
can see EXACTLY which credentials are being sent to Pharmapi and what
the API returns. Designed to debug the "invalid credentials" failure
mode where seed.py reports auth failure even though the credentials look
correct in .env.

Five steps, in order. Stops at the first one that fails so you can
inspect the cause:

  1. Show env vars actually present in this process (redacted).
  2. Show what get_settings() resolves them to (after dotenv load).
  3. Hit Pharmapi /user/me directly with raw httpx — bypasses any
     PharmAssist code paths so you can see the upstream response.
  4. Run _validate() against the live response — exercises the
     extraction logic without touching the DB.
  5. Run full seed() and verify all 4 seeded tables have exactly one
     row each.

Run via the wrapper (recommended — handles env loading for you):

    ./backend/scripts/test_seed.sh

Or directly:

    docker compose run --rm \\
      -e DATABASE_URL=postgresql+asyncpg://pharmassist:pharmassist_dev@db:5432/pharmassist \\
      -e CREDENTIAL_ENCRYPTION_KEY=... \\
      -e PHARMAPI_USERNAME=medcare1pharmapi \\
      -e PHARMAPI_PASSWORD=... \\
      backend python -m scripts.test_seed
"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.pharmapi import verify_pharmapi_credentials
from scripts.seed import _validate, seed


GREEN = "\033[92m"
RED = "\033[91m"
YEL = "\033[93m"
DIM = "\033[2m"
RST = "\033[0m"


def section(num: int, total: int, title: str) -> None:
    print(f"\n{YEL}[{num}/{total}] {title}{RST}")


def show_env(name: str) -> None:
    val = os.environ.get(name)
    if val is None:
        print(f"  {RED}MISSING{RST}  {name}")
        return
    if len(val) <= 6:
        print(f"  {DIM}set    {RST} {name} = {val!r}  (len={len(val)})")
    else:
        masked = f"{val[:4]}…{val[-3:]}"
        print(f"  {DIM}set    {RST} {name} = {masked}  (len={len(val)}, repr={val!r})")


def diagnose_secret(label: str, value: str) -> None:
    """Print byte-level info about a credential so off-by-one issues
    (trailing whitespace, history-expansion mangling, encoding) jump out."""
    if not value:
        print(f"  {RED}{label}: empty{RST}")
        return
    print(f"  {label}:")
    print(f"    repr  = {value!r}")
    print(f"    len   = {len(value)}")
    print(f"    bytes = {value.encode().hex(' ')}")
    if value != value.strip():
        print(f"    {RED}WARNING: leading/trailing whitespace present{RST}")
    if any(ord(c) > 127 for c in value):
        print(f"    {YEL}NOTE: contains non-ASCII characters{RST}")


async def main() -> int:
    print(f"{YEL}=== seed diagnostic ==={RST}")

    section(1, 5, "Environment variables visible to this process")
    for k in (
        "DATABASE_URL",
        "CREDENTIAL_ENCRYPTION_KEY",
        "PHARMAPI_USERNAME",
        "PHARMAPI_PASSWORD",
        "PHARMAPI_API_KEY",
    ):
        show_env(k)

    section(2, 5, "Settings resolved by get_settings()")
    s = get_settings()
    print(f"  pharmapi_base     = {s.pharmapi_base}")
    print(f"  pharmapi_username = {s.pharmapi_username!r}")
    diagnose_secret("pharmapi_password", s.pharmapi_password)
    if s.pharmapi_api_key:
        masked = f"{s.pharmapi_api_key[:4]}…{s.pharmapi_api_key[-3:]}"
        print(f"  pharmapi_api_key  = {masked}  (len={len(s.pharmapi_api_key)})")
    else:
        print(f"  {RED}pharmapi_api_key  = EMPTY{RST}")
    print(f"  database_url      = {s.database_url}")

    section(3, 5, "Hitting Pharmapi /user/me directly (raw httpx, no PharmAssist plumbing)")
    url = f"{s.pharmapi_base}/api/v1/user/me"
    print(f"  URL  : {url}")
    print(f"  Auth : ({s.pharmapi_username!r}, <password from step 2>)")
    print(f"  Hdrs : Api-Key=<from step 2>, Accept=application/json")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                url,
                auth=(s.pharmapi_username, s.pharmapi_password),
                headers={"Accept": "application/json", "Api-Key": s.pharmapi_api_key},
            )
    except Exception as e:
        print(f"  {RED}network exception{RST}: {e!r}")
        return 1

    body = r.text
    snippet = body[:300] + ("…" if len(body) > 300 else "")
    print(f"  Status: {r.status_code}")
    print(f"  Body  : {snippet}")
    if r.status_code != 200:
        print(f"\n  {RED}FAIL{RST} — Pharmapi rejected this request. Hints:")
        if "G15" in body:
            print("    G15 → Api-Key missing from request")
        if "G11" in body:
            print("    G11 → Api-Key invalid; PHARMAPI_API_KEY value is wrong")
        if "G14" in body or "Connection time" in body:
            print("    G14 → 24h Pharmapi session expired; log into the ΗΔΥΚΑ web UI once, then retry")
        if r.status_code == 401:
            print("    401 → Pharmapi rejected username/password. Common causes:")
            print("          - trailing whitespace in PHARMAPI_PASSWORD (compare bytes in step 2)")
            print("          - '!' got history-expanded by an interactive shell — use single quotes or .env")
            print("          - password was rotated upstream but .env still has the old one")
            print("          - api key is for a different pharmacist account")
        return 1
    print(f"  {GREEN}OK{RST} — auth succeeded")

    section(4, 5, "Running _validate() against the live /user/me response")
    try:
        profile = await verify_pharmapi_credentials(s.pharmapi_username, s.pharmapi_password)
        sp = _validate(profile)
    except SystemExit as e:
        print(f"  {RED}_validate() rejected the response{RST}: {e}")
        return 1
    except Exception as e:
        print(f"  {RED}exception{RST}: {e!r}")
        return 1
    print(f"  {GREEN}OK{RST} — extracted SeedProfile:")
    print(f"    pharmacy       : {sp.pharmacy_name}  (unit_id={sp.pharmacy_unit_id})")
    print(f"    pharmacist     : {sp.pharmacist_full_name} <{sp.pharmacist_email}>")
    print(f"    eof_licence_no : {sp.pharmacist_eof_licence_no}")
    print(f"    amka           : {sp.pharmacist_amka}")

    section(5, 5, "Running full seed() and verifying row counts")
    try:
        await seed()
    except Exception as e:
        print(f"  {RED}seed() raised{RST}: {e!r}")
        return 1

    async with AsyncSessionLocal() as db:
        all_ok = True
        for table in ("pharmacies", "pharmacists", "pharmacist_pharmacies", "patient_conditions"):
            n = (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            if n == 1:
                print(f"  {GREEN}OK  {RST} {table}: 1 row")
            else:
                print(f"  {RED}FAIL{RST} {table}: {n} rows (expected 1)")
                all_ok = False

    if all_ok:
        print(f"\n{GREEN}=== all 5 steps passed ==={RST}")
        return 0
    else:
        print(f"\n{RED}=== seed completed but row counts are wrong ==={RST}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
