"""Shared live-mode prescription resolution + safety evaluation.

Both the prescription-detail endpoint (GET /prescriptions/{barcode}) and the
safety-checks sidecar (GET /safety-checks/{barcode}) need the SAME live path:
resolve the ΗΔΥΚΑ prescription by barcode, resolve each therapy line's ATC
from drug_catalog, shape it for the engine, and evaluate. Keeping that in one
place is what stops the two views disagreeing — the bug where the detail card
loaded but the safety panel 404'd because only the detail endpoint had the
live path.

fire-and-forget side effects (scan log, SPC fetch) are NOT done here — they
belong to the detail endpoint only, so the sidecar call never double-fires.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.safety import SafetyChecksPayload
from .drug_catalog import atc_codes_for_barcodes
from .pharmapi import pharmapi_get_prescription, pharmapi_search_prescriptions
from .safety_engine import checks_for_prescription, live_rx_to_engine_shape


async def fetch_live_rx(rx_id: str, pharmacy, doctor_ip: str) -> dict | None:
    """Resolve ONE live prescription by barcode.

    Primary: ``pharmapi_get_prescription`` (GET /prescriptions/get/{barcode}) —
    the source CDA, which surfaces PAPERLESS (άυλη) prescriptions and carries
    the real per-line therapy ids. On 404/422 fall back to ``/search``. Returns
    the search-shaped rx dict, or None. Re-raises a 422 upstream refusal when
    search also comes up empty (so the real ΗΔΥΚΑ message reaches the user).
    """
    primary_exc: HTTPException | None = None
    try:
        return await pharmapi_get_prescription(
            barcode=rx_id, pharmacy_id=pharmacy.pharmapi_unit_id, doctor_ip=doctor_ip
        )
    except HTTPException as exc:
        if exc.status_code not in (404, 422):
            raise
        primary_exc = exc
    results = await pharmapi_search_prescriptions(barcode=rx_id)
    if results:
        return results[0]
    if primary_exc is not None and primary_exc.status_code == 422:
        raise primary_exc
    return None


def shape_live_rx(rx: dict, atc_map: dict[str, str]) -> dict:
    """Engine-shaped rx from a live rx dict + a barcode→ATC map.

    Adds a ``medications`` list (one per therapy line, each with its resolved
    ATC) to ``rx`` in place AND returns the engine-shape dict the safety engine
    consumes — so multi-medicine prescriptions get per-line evaluation and the
    UI can render one card per medicine.
    """
    medicine_barcode = rx.get("medicineBarcode")
    atc = atc_map.get(medicine_barcode) if medicine_barcode else None
    shaped = live_rx_to_engine_shape(rx, atc)
    lines = rx.get("therapyLines") or []
    if lines:
        rx["medications"] = [
            {
                "drugName": ln.get("name"),
                "atcCode": atc_map.get(ln.get("medicineBarcode")),
                "nhrn": ln.get("medicineBarcode"),
            }
            for ln in lines
        ]
        shaped["medications"] = [
            {"atcCode": m["atcCode"]} for m in rx["medications"] if m["atcCode"]
        ]
    return shaped


async def resolve_live_rx_with_checks(
    session: AsyncSession, rx_id: str, pharmacy, doctor_ip: str
) -> tuple[dict | None, SafetyChecksPayload | None]:
    """Fetch a live prescription, resolve ATCs, evaluate safety.

    Returns ``(rx_with_medications, payload)`` or ``(None, None)`` when the
    barcode resolves to nothing.
    """
    rx = await fetch_live_rx(rx_id, pharmacy, doctor_ip)
    if rx is None:
        return None, None
    lines = rx.get("therapyLines") or []
    line_barcodes = [ln.get("medicineBarcode") for ln in lines if ln.get("medicineBarcode")]
    medicine_barcode = rx.get("medicineBarcode")
    barcodes = line_barcodes or ([medicine_barcode] if medicine_barcode else [])
    atc_map = await atc_codes_for_barcodes(session, barcodes)
    shaped = shape_live_rx(rx, atc_map)
    payload = await checks_for_prescription(session, shaped["rxId"], shaped, pharmacy.id)
    return rx, payload
