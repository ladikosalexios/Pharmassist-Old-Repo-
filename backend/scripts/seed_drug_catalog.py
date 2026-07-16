"""Paginate Pharmapi /masterdata/medicines and upsert into drug_catalog.

Usage (from backend/):
    python -m scripts.seed_drug_catalog                       # full sync
    python -m scripts.seed_drug_catalog --since 2026-05-01   # incremental

Requires PHARMAPI_MOCK=false (the mock branch returns an empty catalogue).
Delegates to services.drug_catalog.run_sync, which records a
catalog_sync_runs row — check GET /admin/sync-drug-catalog/status or the
log line it emits for the fetched/upserted/skipped summary.
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.drug_catalog import run_sync

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync Pharmapi medicine catalogue into drug_catalog."
    )
    parser.add_argument("--since", default=None, help="ISO date YYYY-MM-DD for incremental update")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    label = f"since {args.since}" if args.since else "full catalogue"
    print(f"[seed_drug_catalog] Starting sync ({label})...")
    asyncio.run(run_sync(args.since, triggered_by="scripts.seed_drug_catalog"))
