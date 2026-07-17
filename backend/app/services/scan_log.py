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

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.models.patient import Patient
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
    patient_name = rx.get("patientName") or patient.get("name")

    # Passive patient registry: upsert the patient on every visit (scan), so
    # "recent patients" and lookups work from data this pharmacy actually saw.
    if amka:
        profile = patient_payload or {}
        try:
            async with AsyncSessionLocal() as session:
                stmt = pg_insert(Patient).values(
                    pharmacy_id=pharmacy_id,
                    amka=str(amka),
                    name=profile.get("name") or patient_name,
                    age=profile.get("age") if isinstance(profile.get("age"), int) else None,
                    sex=profile.get("sex"),
                    phone=profile.get("phone"),
                    profile=_jsonable(patient_payload) if patient_payload else None,
                    last_seen_at=func.now(),
                )
                update_cols = {
                    "name": stmt.excluded.name,
                    "last_seen_at": func.now(),
                }
                if patient_payload:
                    # Only overwrite the richer fields when THIS visit's lookup
                    # succeeded — a failed snapshot must not blank a good one.
                    update_cols.update(
                        age=stmt.excluded.age,
                        sex=stmt.excluded.sex,
                        phone=stmt.excluded.phone,
                        profile=stmt.excluded.profile,
                    )
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["pharmacy_id", "amka"], set_=update_cols
                    )
                )
                await session.commit()
        except Exception:
            _log.warning("scan log: patient upsert failed for %s", barcode, exc_info=True)

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
                    patient_name=patient_name,
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


def _queue_label(rx: dict) -> str | None:
    meds = rx.get("medications")
    if isinstance(meds, list) and meds:
        first = meds[0].get("drugName") if isinstance(meds[0], dict) else None
        extra = len(meds) - 1
        return f"{first} +{extra}" if first and extra > 0 else first
    m = rx.get("medication")
    if isinstance(m, dict):
        return m.get("drugName")
    return m


async def recent_scan_queue(session, pharmacy_id, limit: int = 30) -> list[dict]:
    """Recent scans as dashboard queue items (latest row per barcode).

    Live mode's "queue": ΗΔΥΚΑ has no pull-based pending feed, so the list a
    pharmacist can act on IS what they scanned — newest first.
    """
    from sqlalchemy import select

    rows = (
        await session.scalars(
            select(PrescriptionScan)
            .where(PrescriptionScan.pharmacy_id == pharmacy_id)
            .order_by(PrescriptionScan.barcode, PrescriptionScan.created_at.desc())
            .distinct(PrescriptionScan.barcode)
        )
    ).all()
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return [
        {
            "rxId": r.barcode,
            "patientName": r.patient_name or "Άγνωστος",
            "medication": _queue_label(r.rx_payload or {}),
            "physician": (r.rx_payload or {}).get("physician"),
            "date": (r.rx_payload or {}).get("date") or r.created_at.date().isoformat(),
            "status": r.status,
        }
        for r in rows[:limit]
    ]
