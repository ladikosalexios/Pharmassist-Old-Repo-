"""Fire-and-forget scan log — persist every resolved barcode scan.

One row per scan in ``prescription_scans``: the full normalized prescription
payload (incl. therapy lines + the safety-check snapshot) plus a best-effort
patient snapshot (demographics + intolerances via ``patients.resolve``).

Runs as a tracked background task (the audit-log pattern from PR #76): the
scan response returns immediately, the row lands right after, and the
``_background_tasks`` strong-reference set + the ``main.py`` shutdown drain
guarantee a graceful restart doesn't drop the last scan. Failures are logged,
never raised — a broken scan log must not break the counter.
"""

import asyncio
import json
import logging
import uuid

from ..db.models.prescription_scan import PrescriptionScan
from ..db.session import AsyncSessionLocal
from .audit import _background_tasks

_log = logging.getLogger(__name__)


def _jsonable(value):
    """Round-trip through json with ``default=str`` so datetimes / UUIDs in the
    safety-check snapshot never break the JSONB insert."""
    return json.loads(json.dumps(value, default=str))


async def _record_scan(
    *,
    pharmacy_id: uuid.UUID,
    pharmacist_id: uuid.UUID,
    barcode: str,
    rx: dict,
    source: str,
) -> None:
    patient_payload = None
    amka = rx.get("patientAmka") or (rx.get("patient") or {}).get("amka")
    if amka:
        try:
            from .patients import resolve

            patient_payload = await resolve(str(amka))
        except Exception:
            _log.warning("scan log: patient snapshot failed for %s", barcode, exc_info=True)

    patient = rx.get("patient") if isinstance(rx.get("patient"), dict) else {}
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                PrescriptionScan(
                    pharmacy_id=pharmacy_id,
                    pharmacist_id=pharmacist_id,
                    barcode=barcode,
                    status=rx.get("status") or "UNKNOWN",
                    pharmapi_status=rx.get("pharmApiStatus"),
                    patient_amka=str(amka) if amka else None,
                    patient_name=rx.get("patientName") or patient.get("name"),
                    source=source,
                    rx_payload=_jsonable(rx),
                    patient_payload=_jsonable(patient_payload) if patient_payload else None,
                )
            )
            await session.commit()
    except Exception:
        _log.warning("scan log failed for %s", barcode, exc_info=True)


def fire_scan_record(**kwargs) -> None:
    """Schedule ``_record_scan`` as a tracked fire-and-forget task."""
    task = asyncio.create_task(_record_scan(**kwargs))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
