"""PDF rendering for documentation exports.

Optional dependency: ``reportlab``. When it isn't installed,
``REPORTLAB_AVAILABLE`` is False and the documentation router falls back to
CSV (see ``services.documentation.csv_response``). Keeping the import wrapped
here means the rest of the app never has to know reportlab is optional.
"""

import io
from datetime import UTC, datetime

from fastapi.responses import StreamingResponse

try:
    from reportlab.lib import colors as _rl_colors
    from reportlab.lib.pagesizes import A4 as _RL_A4
    from reportlab.lib.styles import getSampleStyleSheet as _rl_styles
    from reportlab.lib.units import cm as _RL_CM
    from reportlab.platypus import (
        Paragraph as _RLParagraph,
    )
    from reportlab.platypus import (
        SimpleDocTemplate as _RLSimpleDocTemplate,
    )
    from reportlab.platypus import (
        Spacer as _RLSpacer,
    )
    from reportlab.platypus import (
        Table as _RLTable,
    )
    from reportlab.platypus import (
        TableStyle as _RLTableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


PHARMACY_NAME = "MedCare Pharmacy"
PHARMACY_LICENCE = "PHC-2024-1138"
PHARMACIST_LICENCE = "PH-12345"
RETENTION_NOTICE = (
    "Records are retained for the legally required period (minimum 5 years per the Εθνικός "
    "Οργανισμός Φαρμάκων (Ε.Ο.Φ.) record-retention rules) and are accessible for audits and "
    "inspections. Each entry includes pharmacist signature, timestamp, and delivery confirmation."
)


def safe_filename_part(s: str) -> str:
    out = "".join(c if c.isalnum() else "_" for c in (s or "")).strip("_")
    return out or "record"


def full_report(rows: list, current: dict) -> bytes:
    """Render the full Documentation & Legal Log as a PDF. Requires reportlab."""
    buf = io.BytesIO()
    doc = _RLSimpleDocTemplate(
        buf,
        pagesize=_RL_A4,
        leftMargin=1.6 * _RL_CM,
        rightMargin=1.6 * _RL_CM,
        topMargin=1.8 * _RL_CM,
        bottomMargin=1.8 * _RL_CM,
        title="PharmAssist Documentation & Legal Log",
    )
    styles = _rl_styles()
    title = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    elements = []
    generated_at = datetime.now(UTC).isoformat()
    if rows:
        oldest = min(r["dispensedAt"] for r in rows)[:10]
        newest = max(r["dispensedAt"] for r in rows)[:10]
        date_range = f"{oldest} – {newest}"
    else:
        date_range = "—"

    elements.append(_RLParagraph("PharmAssist — Documentation & Legal Log", title))
    elements.append(_RLSpacer(1, 0.3 * _RL_CM))
    elements.append(
        _RLParagraph(
            f"<b>Pharmacy:</b> {PHARMACY_NAME} (Licence {PHARMACY_LICENCE})<br/>"
            f"<b>Pharmacist:</b> {current.get('name', '')} (Licence {PHARMACIST_LICENCE})<br/>"
            f"<b>Date range:</b> {date_range}<br/>"
            f"<b>Records:</b> {len(rows)}<br/>"
            f"<b>Generated:</b> {generated_at}",
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.5 * _RL_CM))

    table_data = [["Date", "Rx", "Patient", "Drug", "Method", "Language", "Setting"]]
    for r in rows:
        table_data.append(
            [
                r["dispensedAt"][:10],
                r["rxId"],
                r["patientName"],
                r["drugName"],
                (r["deliveryMethod"] or "").title(),
                r["language"],
                r["setting"],
            ]
        )
    table = _RLTable(table_data, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        _RLTableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_colors.HexColor("#DBEAFE")),
                ("TEXTCOLOR", (0, 0), (-1, 0), _rl_colors.HexColor("#1E40AF")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, _rl_colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(table)
    elements.append(_RLSpacer(1, 0.6 * _RL_CM))

    elements.append(_RLParagraph("Legal Compliance", h2))
    elements.append(
        _RLParagraph(
            "All documentation records are maintained in compliance with pharmacy regulations and "
            "HIPAA requirements. " + RETENTION_NOTICE,
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.6 * _RL_CM))

    elements.append(_RLParagraph("Pharmacist Signature", h2))
    elements.append(
        _RLParagraph(
            f"<b>Name:</b> {current.get('name', '')}<br/>"
            f"<b>Licence:</b> {PHARMACIST_LICENCE}<br/>"
            f"<b>Generated at:</b> {generated_at}<br/><br/>"
            "<i>Electronically signed via PharmAssist.</i>",
            body,
        )
    )

    doc.build(elements)
    return buf.getvalue()


def single_record(rec: dict, current: dict) -> bytes:
    """Render a single documentation record as a one-page PDF."""
    buf = io.BytesIO()
    doc = _RLSimpleDocTemplate(
        buf,
        pagesize=_RL_A4,
        leftMargin=1.8 * _RL_CM,
        rightMargin=1.8 * _RL_CM,
        topMargin=2.0 * _RL_CM,
        bottomMargin=2.0 * _RL_CM,
        title=f"PharmAssist Documentation Record — {rec['id']}",
    )
    styles = _rl_styles()
    title = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    elements = []
    generated_at = datetime.now(UTC).isoformat()

    elements.append(_RLParagraph("PharmAssist — Documentation Record", title))
    elements.append(_RLSpacer(1, 0.4 * _RL_CM))
    elements.append(
        _RLParagraph(
            f"<b>Record:</b> {rec['id']}<br/>"
            f"<b>Pharmacy:</b> {PHARMACY_NAME} (Licence {PHARMACY_LICENCE})<br/>"
            f"<b>Generated:</b> {generated_at}",
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.5 * _RL_CM))

    elements.append(_RLParagraph("Patient", h2))
    elements.append(
        _RLParagraph(
            f"<b>Name:</b> {rec['patientName']}<br/>"
            f"<b>Prescription code:</b> {rec['rxId']}<br/>"
            f"<b>Setting:</b> {rec['setting']}",
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.4 * _RL_CM))

    elements.append(_RLParagraph("Drug", h2))
    elements.append(_RLParagraph(rec["drugName"], body))
    elements.append(_RLSpacer(1, 0.4 * _RL_CM))

    elements.append(_RLParagraph("Counseling Provided", h2))
    elements.append(
        _RLParagraph(
            (rec["informationProvided"] or "").replace("\n", "<br/>"),
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.4 * _RL_CM))

    elements.append(_RLParagraph("Delivery", h2))
    elements.append(
        _RLParagraph(
            f"<b>Language:</b> {rec['language']}<br/>"
            f"<b>Method:</b> {(rec['deliveryMethod'] or '').title()}<br/>"
            f"<b>Dispensed at:</b> {rec['dispensedAt']}",
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.5 * _RL_CM))

    elements.append(_RLParagraph("Pharmacist Signature", h2))
    elements.append(
        _RLParagraph(
            f"<b>Name:</b> PharmD {rec['pharmacistName']}<br/>"
            f"<b>Licence:</b> {rec['pharmacistLicense']}<br/>"
            f"<b>Generated by:</b> {current.get('name', '')} (Licence {PHARMACIST_LICENCE})<br/>"
            f"<b>Timestamp:</b> {generated_at}<br/><br/>"
            "<i>Electronically signed via PharmAssist.</i>",
            body,
        )
    )
    elements.append(_RLSpacer(1, 0.5 * _RL_CM))

    elements.append(_RLParagraph("Retention Notice", h2))
    elements.append(_RLParagraph(RETENTION_NOTICE, body))

    doc.build(elements)
    return buf.getvalue()


def pdf_response(payload: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
