"""Documentation & Legal Log: mock store + filter / stats / CSV response helpers.

PDF rendering lives in ``services.pdf`` (separate so the optional reportlab
dependency stays isolated).
"""

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.documentation_log import DocumentationLog
from ..db.models.pharmacist import Pharmacist
from ..db.models.pharmacist_pharmacy import PharmacistPharmacy
from .security import SECRET_KEY

MOCK_DOCUMENTATION: list = [
    {
        "id": "DOC-2026-0007",
        "rxId": "RX2024-005",
        "patientName": "Maria Stavrou",
        "drugName": "Warfarin 5 mg",
        "setting": "Private",
        "deliveryMethod": "BOTH",
        "language": "Greek",
        "informationProvided": (
            "Reviewed bleeding precautions, INR monitoring schedule, dietary "
            "considerations (vitamin K), and signs of over-anticoagulation. Patient "
            "received printed leaflet and digital copy via the patient portal."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-04-29T10:30:00+00:00",
    },
    {
        "id": "DOC-2026-0006",
        "rxId": "RX2024-001",
        "patientName": "Sarah Johnson",
        "drugName": "Amoxicillin 500 mg",
        "setting": "Private",
        "deliveryMethod": "PRINT",
        "language": "English",
        "informationProvided": (
            "Counselled on full course completion, symptom-watch for hypersensitivity, "
            "and gastrointestinal side effects. Provided printed leaflet."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-04-15T16:02:00+00:00",
    },
    {
        "id": "DOC-2026-0005",
        "rxId": "RX2024-002",
        "patientName": "James Martinez",
        "drugName": "Warfarin 7.5 mg",
        "setting": "Hospital",
        "deliveryMethod": "DIGITAL",
        "language": "English",
        "informationProvided": (
            "Reviewed inpatient protocol with the ward pharmacist and the patient. "
            "Digital counselling pack pushed to the patient's hospital portal."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-04-12T09:18:00+00:00",
    },
    {
        "id": "DOC-2026-0004",
        "rxId": "RX2024-003",
        "patientName": "Maria Garcia",
        "drugName": "Lisinopril 10 mg",
        "setting": "Private",
        "deliveryMethod": "PRINT",
        "language": "Greek",
        "informationProvided": (
            "Discussed renal function monitoring, dry-cough as a possible side effect, "
            "and the need to avoid concurrent NSAIDs. Printed leaflet handed over."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-03-22T11:44:00+00:00",
    },
    {
        "id": "DOC-2026-0003",
        "rxId": "RX2023-118",
        "patientName": "Eleni Nikolaou",
        "drugName": "Atorvastatin 20 mg",
        "setting": "Private",
        "deliveryMethod": "BOTH",
        "language": "Greek",
        "informationProvided": (
            "Reviewed muscle pain warnings and lipid panel follow-up timing. Both "
            "printed leaflet and digital copy delivered."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-03-10T15:05:00+00:00",
    },
    {
        "id": "DOC-2026-0002",
        "rxId": "RX2023-091",
        "patientName": "Dimitrios Konstantinou",
        "drugName": "Metformin 1000 mg",
        "setting": "Hospital",
        "deliveryMethod": "DIGITAL",
        "language": "Greek",
        "informationProvided": (
            "Discussed lactic-acidosis red-flag symptoms and renal function checks. "
            "Digital counselling sent to the inpatient app."
        ),
        "pharmacistName": "Demo Pharmacist",
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": "2026-02-27T08:51:00+00:00",
    },
]


def stats() -> dict:
    s = {"total": len(MOCK_DOCUMENTATION), "print": 0, "digital": 0, "both": 0}
    for d in MOCK_DOCUMENTATION:
        m = d["deliveryMethod"]
        if m == "PRINT":
            s["print"] += 1
        elif m == "DIGITAL":
            s["digital"] += 1
        elif m == "BOTH":
            s["both"] += 1
    return s


def filter_records(query: str | None, method: str | None) -> list:
    items = list(MOCK_DOCUMENTATION)
    if query:
        q = query.lower().strip()
        items = [
            d
            for d in items
            if q in d["patientName"].lower() or q in d["rxId"].lower() or q in d["drugName"].lower()
        ]
    if method and method.upper() != "ALL":
        items = [d for d in items if d["deliveryMethod"] == method.upper()]
    items.sort(key=lambda d: d["dispensedAt"], reverse=True)
    return items


def csv_response(rows: list, filename: str) -> StreamingResponse:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "ID",
            "Dispensed At",
            "Rx Code",
            "Patient",
            "Drug",
            "Setting",
            "Delivery Method",
            "Language",
            "Information Provided",
            "Pharmacist",
            "Licence",
            "Signature Confirmed",
        ]
    )
    for d in rows:
        writer.writerow(
            [
                d["id"],
                d["dispensedAt"],
                d["rxId"],
                d["patientName"],
                d["drugName"],
                d["setting"],
                d["deliveryMethod"],
                d["language"],
                d["informationProvided"],
                d["pharmacistName"],
                d["pharmacistLicense"],
                "yes" if d["signatureConfirmed"] else "no",
            ]
        )
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def mark_exported(records: list) -> str:
    """Stamp an exportedAt on each record (immutability marker) and return the timestamp."""
    ts = datetime.now(UTC).isoformat()
    for r in records:
        r.setdefault("exportedAt", ts)
        # Once exported, records are considered immutable. We don't update further.
    return ts


# ── Prescription action audit (DB-backed) ─────────────────────────────────────


async def _resolve_pharmacist_default_pharmacy(session: AsyncSession, email: str) -> tuple:
    """Look up (pharmacist_id, pharmacy_id, eof_licence_no) for a JWT-authenticated user.

    Joins pharmacists → pharmacist_pharmacies on the default link. The seed
    script always creates exactly one default link per pharmacist; if a
    pharmacist somehow has none, that's a data-integrity bug — fail loud.
    """
    stmt = (
        select(
            Pharmacist.id,
            Pharmacist.eof_licence_no,
            PharmacistPharmacy.pharmacy_id,
        )
        .join(PharmacistPharmacy, PharmacistPharmacy.pharmacist_id == Pharmacist.id)
        .where(func.lower(Pharmacist.email) == email.lower())
        .where(PharmacistPharmacy.is_default.is_(True))
    )
    row = (await session.execute(stmt)).first()
    if not row:
        raise HTTPException(
            status_code=401,
            detail=f"No default-pharmacy link for {email}. Run scripts/seed.py.",
        )
    return row[0], row[2], row[1]


def _signature(pharmacist_id, barcode: str, dispensed_at: datetime) -> str:
    payload = f"{pharmacist_id}{barcode}{dispensed_at.isoformat()}{SECRET_KEY}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def record_prescription_action(
    session: AsyncSession,
    *,
    action_type: Literal["APPROVE", "FLAG"],
    rx: dict,
    safety_checks: list,
    pharmacist_email: str,
    pharmapi_exec_ref: str | None,
    discrepancy_type: str | None,
    notes: str | None,
    info_provided: str | None,
    delivery_method: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> DocumentationLog:
    """Persist a documentation_logs row for an approve/flag action.

    Single write path used by both POST /prescriptions/{id}/approve and
    PATCH /prescriptions/{id} when status flips to FLAGGED. Computes the
    pharmacist_signature documented on the model and commits.
    """
    pharmacist_id, pharmacy_id, _ = await _resolve_pharmacist_default_pharmacy(
        session, pharmacist_email
    )

    dispensed_at = datetime.now(UTC)
    row = DocumentationLog(
        pharmacist_id=pharmacist_id,
        pharmacy_id=pharmacy_id,
        action_type=action_type,
        prescription_barcode=rx["rxId"],
        patient_amka=rx["patient"]["amka"],
        patient_name=rx["patient"]["name"],
        medicine_name=rx["medication"]["drugName"],
        info_provided=info_provided,
        delivery_method=delivery_method,
        discrepancy_type=discrepancy_type,
        notes=notes,
        safety_check_snapshot=safety_checks,
        dispensed_at=dispensed_at,
        pharmapi_exec_ref=pharmapi_exec_ref,
        pharmacist_signature=_signature(pharmacist_id, rx["rxId"], dispensed_at),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
