"""Documentation & Legal Log: mock store + filter / stats / CSV response helpers.

PDF rendering lives in ``services.pdf`` (separate so the optional reportlab
dependency stays isolated).
"""

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi.responses import StreamingResponse


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


def filter_records(query: Optional[str], method: Optional[str]) -> list:
    items = list(MOCK_DOCUMENTATION)
    if query:
        q = query.lower().strip()
        items = [
            d for d in items
            if q in d["patientName"].lower() or q in d["rxId"].lower() or q in d["drugName"].lower()
        ]
    if method and method.upper() != "ALL":
        items = [d for d in items if d["deliveryMethod"] == method.upper()]
    items.sort(key=lambda d: d["dispensedAt"], reverse=True)
    return items


def csv_response(rows: list, filename: str) -> StreamingResponse:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "ID", "Dispensed At", "Rx Code", "Patient", "Drug", "Setting",
        "Delivery Method", "Language", "Information Provided",
        "Pharmacist", "Licence", "Signature Confirmed",
    ])
    for d in rows:
        writer.writerow([
            d["id"], d["dispensedAt"], d["rxId"], d["patientName"], d["drugName"],
            d["setting"], d["deliveryMethod"], d["language"], d["informationProvided"],
            d["pharmacistName"], d["pharmacistLicense"],
            "yes" if d["signatureConfirmed"] else "no",
        ])
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def mark_exported(records: list) -> str:
    """Stamp an exportedAt on each record (immutability marker) and return the timestamp."""
    ts = datetime.now(timezone.utc).isoformat()
    for r in records:
        r.setdefault("exportedAt", ts)
        # Once exported, records are considered immutable. We don't update further.
    return ts
