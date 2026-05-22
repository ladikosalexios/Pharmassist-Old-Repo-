"""Paginate Pharmapi /masterdata/medicines and upsert into drug_catalog.

Usage (from backend/):
    python -m scripts.seed_drug_catalog                       # full sync
    python -m scripts.seed_drug_catalog --since 2026-05-01   # incremental
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import AsyncSessionLocal
from app.services.drug_catalog import sync_drug_catalog


async def main(since: str | None) -> None:
    label = f"since {since}" if since else "full catalogue"
    print(f"[seed_drug_catalog] Starting sync ({label})...")
    async with AsyncSessionLocal() as db:
        summary = await sync_drug_catalog(db, since=since)
    print(
        f"[seed_drug_catalog] Done — "
        f"fetched={summary['fetched']}  upserted={summary['upserted']}  skipped={summary['skipped']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Pharmapi medicine catalogue into drug_catalog.")
    parser.add_argument("--since", default=None, help="ISO date YYYY-MM-DD for incremental update")
    args = parser.parse_args()
    asyncio.run(main(args.since))
