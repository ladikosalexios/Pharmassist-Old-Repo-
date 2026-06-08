"""Pharmacovigilance / adverse drug reaction reports (mock).

Severity: MILD | MODERATE | SEVERE.
Status:   PENDING_REVIEW | ESCALATED | EOF_REPORTED.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.adr_report import AdrReport

from ..constants import AdrCausality, AdrSeverity, AdrStatus

MOCK_SIDE_EFFECTS: list = [
    {
        "id": "ADR-2026-0009",
        "patientId": "P001",
        "patientName": "Maria Stavrou",
        "patientPhone": "+30 694 312 3456",
        "rxId": "RX2024-005",
        "drugName": "Warfarin 5 mg",
        "severity": AdrSeverity.SEVERE,
        "status": AdrStatus.ESCALATED,
        "reportedAt": "2026-04-29T16:42:00+00:00",
        "symptom": "Dark stools, dizziness on standing, gum bleeding after brushing teeth.",
        "onset": "8 hours after the second dose",
        "causality": AdrCausality.PROBABLE,
    },
    {
        "id": "ADR-2026-0008",
        "patientId": "P004",
        "patientName": "Eleni Papadopoulos",
        "patientPhone": "+30 697 555 0142",
        "rxId": "RX2024-002",
        "drugName": "Warfarin 7.5 mg",
        "severity": AdrSeverity.MODERATE,
        "status": AdrStatus.PENDING_REVIEW,
        "reportedAt": "2026-04-28T11:05:00+00:00",
        "symptom": "Persistent nosebleeds and unusual bruising on forearms.",
        "onset": "Within 48 hours of dose increase",
        "causality": AdrCausality.PROBABLE,
    },
    {
        "id": "ADR-2026-0007",
        "patientId": "P010",
        "patientName": "Sarah Johnson",
        "patientPhone": "+30 698 011 2233",
        "rxId": "RX2024-001",
        "drugName": "Amoxicillin 500 mg",
        "severity": AdrSeverity.MILD,
        "status": AdrStatus.PENDING_REVIEW,
        "reportedAt": "2026-04-26T08:20:00+00:00",
        "symptom": "Diffuse maculopapular rash on torso, no breathing difficulty.",
        "onset": "Day 3 of antibiotic course",
        "causality": AdrCausality.POSSIBLE,
    },
    {
        "id": "ADR-2026-0006",
        "patientId": "P012",
        "patientName": "Dimitrios Konstantinou",
        "patientPhone": "+30 698 555 7012",
        "rxId": None,
        "drugName": "Atorvastatin 20 mg",
        "severity": AdrSeverity.SEVERE,
        "status": AdrStatus.EOF_REPORTED,
        "reportedAt": "2026-04-22T19:14:00+00:00",
        "symptom": "Generalised muscle pain, dark urine, ALT 5x upper limit.",
        "onset": "Three weeks after starting therapy",
        "causality": AdrCausality.PROBABLE,
    },
    {
        "id": "ADR-2026-0005",
        "patientId": "P020",
        "patientName": "Anna Kostas",
        "patientPhone": "+30 697 999 0011",
        "rxId": None,
        "drugName": "Clopidogrel 75 mg",
        "severity": AdrSeverity.MODERATE,
        "status": AdrStatus.ESCALATED,
        "reportedAt": "2026-04-15T12:00:00+00:00",
        "symptom": "Two episodes of melena, mild dyspnoea on exertion.",
        "onset": "Two weeks into therapy",
        "causality": AdrCausality.POSSIBLE,
    },
    {
        "id": "ADR-2026-0004",
        "patientId": "P031",
        "patientName": "Nikos Vlachos",
        "patientPhone": "+30 698 222 0099",
        "rxId": None,
        "drugName": "Metformin 1000 mg",
        "severity": AdrSeverity.MILD,
        "status": AdrStatus.EOF_REPORTED,
        "reportedAt": "2026-03-30T10:30:00+00:00",
        "symptom": "Mild gastrointestinal upset and metallic taste.",
        "onset": "First week of therapy",
        "causality": AdrCausality.UNLIKELY,
    },
]

SEVERITY_RANK = {AdrSeverity.MILD: 0, AdrSeverity.MODERATE: 1, AdrSeverity.SEVERE: 2}
STATUS_RANK = {AdrStatus.PENDING_REVIEW: 0, AdrStatus.ESCALATED: 1, AdrStatus.EOF_REPORTED: 2}


async def count_report_stat(session: AsyncSession, stat_name: str, stat_value: str) -> int:
    return await session.scalar(
        select(func.count(AdrReport.id)).where(getattr(AdrReport, stat_name) == stat_value)
    )


async def stats(session: AsyncSession) -> dict:
    s = {
        "total": await session.scalar(select(func.count()).select_from(AdrReport)),
        "pendingReview": await count_report_stat(session, "status", AdrStatus.PENDING_REVIEW),
        "severe": await count_report_stat(session, "severity", AdrSeverity.SEVERE),
        "escalated": await count_report_stat(session, "status", AdrStatus.ESCALATED),
    }
    return s


def next_status(current_status: str) -> str:
    if current_status == AdrStatus.PENDING_REVIEW:
        return AdrStatus.ESCALATED
    if current_status == AdrStatus.ESCALATED:
        return AdrStatus.EOF_REPORTED
    return current_status


def get_adr_report_dict(adr_report: AdrReport) -> dict:
    """Returns a dict representation of the given AdrReport class object."""
    return {
        "id": adr_report.id,
        "patientId": adr_report.patient_amka,
        "patientName": adr_report.patient_name,
        "patientPhone": None,
        "rxId": None,
        "drugName": adr_report.medicine_name,
        "severity": adr_report.severity,
        "status": adr_report.status,
        "reportedAt": str(adr_report.reported_at),
        "symptom": adr_report.symptom_description,
        "onset": adr_report.onset_timing,
        "causality": adr_report.causality,
    }


def search_and_sort_mock(q: str | None, sort: str | None) -> list[dict]:
    """Mock-mode equivalent of the DB query in list_side_effects.

    Mirrors the live free-text search (patient/drug/symptom) and the
    date|severity|status sort so both bridge modes return identical shapes.
    """
    items = list(MOCK_SIDE_EFFECTS)
    if q:
        needle = q.lower().strip()
        items = [
            r
            for r in items
            if needle in r["patientName"].lower()
            or needle in r["drugName"].lower()
            or needle in r["symptom"].lower()
        ]
    sort_key = (sort or "date").lower()
    if sort_key == "severity":
        items.sort(
            key=lambda r: (SEVERITY_RANK.get(r["severity"], -1), r["reportedAt"]),
            reverse=True,
        )
    elif sort_key == "status":
        items.sort(
            key=lambda r: (STATUS_RANK.get(r["status"], -1), r["reportedAt"]),
            reverse=True,
        )
    else:
        items.sort(key=lambda r: r["reportedAt"], reverse=True)
    return items


def mock_stats() -> dict:
    """In-memory counterpart to stats() for mock mode."""
    return {
        "total": len(MOCK_SIDE_EFFECTS),
        "pendingReview": sum(
            1 for r in MOCK_SIDE_EFFECTS if r["status"] == AdrStatus.PENDING_REVIEW
        ),
        "severe": sum(1 for r in MOCK_SIDE_EFFECTS if r["severity"] == AdrSeverity.SEVERE),
        "escalated": sum(1 for r in MOCK_SIDE_EFFECTS if r["status"] == AdrStatus.ESCALATED),
    }


def create_mock_side_effect(
    *,
    patient_id: str | None,
    patient_name: str,
    rx_id: str | None,
    drug_name: str,
    severity: str,
    symptom: str,
    onset: str,
    causality: str | None,
) -> dict:
    """Append a new report to the in-memory list used by GET in mock mode.

    Returns the exact camelCase SideEffectReport shape the list endpoint
    returns, status PENDING_REVIEW and reportedAt = now (UTC).
    """
    record = {
        "id": f"ADR-{uuid.uuid4().hex[:8].upper()}",
        "patientId": patient_id,
        "patientName": patient_name,
        "patientPhone": None,
        "rxId": rx_id,
        "drugName": drug_name,
        "severity": severity,
        "status": AdrStatus.PENDING_REVIEW,
        "reportedAt": datetime.now(UTC).isoformat(),
        "symptom": symptom,
        "onset": onset,
        "causality": causality,
    }
    MOCK_SIDE_EFFECTS.append(record)
    return record
