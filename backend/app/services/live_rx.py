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
            {"atcCode": m["atcCode"], "nhrn": m.get("nhrn"), "drugName": m.get("drugName")}
            for m in rx["medications"]
            if m["atcCode"]
        ]
    return shaped


async def _load_profile(amka) -> dict:
    """Best-effort patient profile (age/sex/intolerances). A failed lookup never
    breaks the review page — callers degrade to an empty dict."""
    if not amka:
        return {}
    try:
        from .patients import resolve

        return await resolve(str(amka)) or {}
    except Exception:
        return {}


async def shape_live_response(rx: dict, checks: list) -> dict:
    """Shape a flat live rx into the frontend's nested Prescription contract.

    ΗΔΥΚΑ returns a FLAT rx (patientName/medication-string/physician); the SPA
    was built against the mock's NESTED shape (patient{}, medication{},
    prescriber{}). Bridging here — not in the SPA — keeps mock and live in
    lockstep (CLAUDE.md). Patient demographics (age/allergies) are enriched
    best-effort from the patient profile; a failed lookup never breaks the
    review page — the name/AMKA/drug/prescriber/safety all still render.
    """
    meds = rx.get("medications") or []
    first = meds[0] if meds else {}
    med_name = first.get("drugName") or (
        rx.get("medication") if isinstance(rx.get("medication"), str) else ""
    )

    amka = rx.get("patientAmka")
    # Reuse the profile resolve_live_rx_with_checks already fetched (stashed on
    # rx) so a scan makes ONE ΗΔΥΚΑ patient call, not two.
    profile = rx["_profile"] if "_profile" in rx else await _load_profile(amka)
    allergies = _allergy_summary(profile)

    return {
        "rxId": rx.get("rxId"),
        "code": rx.get("rxId"),
        "dateIssued": rx.get("date"),
        "expiryDate": rx.get("expiryDate"),
        "status": rx.get("status"),
        "pharmApiStatus": rx.get("pharmApiStatus"),
        "spcVersion": "",
        "patient": {
            "id": amka,
            "name": rx.get("patientName") or "—",
            "age": profile.get("age"),
            "dateOfBirth": profile.get("dateOfBirth") or "",
            "amka": amka or "",
            "conditions": profile.get("conditions") or [],
            "allergies": allergies,
        },
        "medication": {
            "drugName": med_name,
            "atcCode": first.get("atcCode"),
            "nhrn": first.get("nhrn") or rx.get("medicineBarcode"),
            "dose": "",
            "form": "",
            "route": "",
            "frequency": "",
            "treatmentDuration": "",
            "spcRecommendedDosage": "",
        },
        "medications": meds,
        "prescriber": {
            "name": rx.get("physician") or "—",
            "licenceId": "",
            "specialty": "",
            "contact": "",
            "email": "",
        },
        "spcQuickReference": {"contraindications": [], "majorInteractions": []},
        "safetyChecks": checks,
    }


def _allergy_summary(profile: dict) -> str:
    """Distinct intolerance substances as a display string. ΗΔΥΚΑ intolerances
    are dicts ({activeSubstance, intolerance, remarks}); the profile may also
    carry a plain ``allergies`` string/list."""
    names: list[str] = []
    for item in profile.get("intolerances") or []:
        if isinstance(item, dict):
            n = item.get("activeSubstance") or item.get("name")
        else:
            n = item if isinstance(item, str) else None
        if n and n not in names:
            names.append(str(n))
    if names:
        return ", ".join(names)
    a = profile.get("allergies")
    return ", ".join(a) if isinstance(a, list) else (a or "")


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
    # Fetch the patient profile ONCE: the engine needs age (age-bracket factor
    # gating) and shape_live_response reuses it via rx["_profile"] — one ΗΔΥΚΑ
    # patient call per scan. Stashed on the raw rx, which is never persisted (the
    # scan snapshot stores the shaped response, not this dict).
    profile = await _load_profile(rx.get("patientAmka"))
    rx["_profile"] = profile
    shaped["patient"]["age"] = profile.get("age")
    shaped["patient"]["sex"] = profile.get("sex")
    payload = await checks_for_prescription(
        session, shaped["rxId"], shaped, pharmacy.id, verbose_spc=True
    )
    return rx, payload
