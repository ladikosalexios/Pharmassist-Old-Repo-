"""Bulk-ingest curated SPC/PIL PDFs from a local manifest into ``spc_documents``.

Usage (from ``backend/`` or inside the ``backend`` container):
    python -m scripts.import_spc_dir
    python -m scripts.import_spc_dir --manifest data/manifest.json

Idempotent: ``ingest_pdf_bytes`` deduplicates by ``(barcode, doc_type, sha256)``,
so re-running after adding new PDFs only ingests new files.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import AsyncSessionLocal
from app.services.spc_ingest import ingest_pdf_bytes

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "data" / "manifest.json"


async def import_manifest(manifest_path: Path) -> int:
    """Ingest every entry in ``manifest_path`` and print per-document status."""
    base_dir = manifest_path.parent
    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = 0

    async with AsyncSessionLocal() as db:
        for idx, item in enumerate(items):
            try:
                fname = item["file"]
                atc_code = item["atc_code"]
                pdf_path = base_dir / fname
                if not pdf_path.is_file():
                    print(f"MISSING  {atc_code} | {pdf_path}", file=sys.stderr)
                    failures += 1
                    continue

                doc = await ingest_pdf_bytes(
                    db,
                    pdf=pdf_path.read_bytes(),
                    source=item.get("source", "upload"),
                    doc_type=item.get("doc_type", "spc"),
                    atc_code=atc_code,
                    barcode=item.get("barcode"),
                    source_url=item.get("source_url"),
                    language=item.get("language", "en"),
                )
            except (KeyError, ValueError, OSError) as exc:
                print(f"ERROR    entry[{idx}]: {exc}", file=sys.stderr)
                failures += 1
                continue
            sections = len(doc.sections or {})
            print(
                f"{doc.parse_status.upper():7s}  {doc.atc_code:8s} | "
                f"{fname} | sections={sections} | id={doc.id}"
            )
            if doc.parse_status == "failed":
                failures += 1

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest SPC/PIL PDFs from a manifest.json")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Path to manifest.json (default: {DEFAULT_MANIFEST})",
    )
    args = parser.parse_args()
    return asyncio.run(import_manifest(args.manifest))


if __name__ == "__main__":
    raise SystemExit(main())
