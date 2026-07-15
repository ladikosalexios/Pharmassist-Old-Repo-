"""HL7 CDA parser for retrieved prescriptions (Άντληση Συνταγής).

Spec source: ΗΔΥΚΑ pharmapi v2 OpenAPI doc — ``info.description`` at
``https://testeps.e-prescription.gr/pharmapiv2/v3/api-docs/manufacturers``.

Namespaces and OID roots are pinned to that spec; the golden under
``backend/tests/fixtures/cda/`` is extracted from it verbatim. Do not invent
new template IDs — extend by patching the spec or the fixture and re-running
``tests/test_prescription_cda.py``.

Retrieval-only: the eDispensation CDA *builder* (and dispense-response parser)
was removed with the execution path — see tag ``hmvs-certified``.

PHI guard: the parsed object carries patient identifiers (AMKA, name).
Callers must NOT log the parsed object, only the barcode and outer status.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

# ── Namespaces ──────────────────────────────────────────────────────────────
NS_HL7 = "urn:hl7-org:v3"

# ── OID roots (verbatim from the spec) ──────────────────────────────────────
ROOT_RX_BARCODE = "1.21"
# recordTarget patient AMKA, used when parsing a retrieved prescription CDA
# (Άντληση Συνταγής → GET /api/v1/prescriptions/get/{barcode}).
ROOT_RECORD_TARGET_AMKA = "1.10.1"
ROOT_THERAPY_LINE = "1.21.1"


# ── Prescription retrieval (Άντληση Συνταγής) ───────────────────────────────
# GET /api/v1/prescriptions/get/{barcode} returns the SOURCE prescription as an
# epSOS ePrescription CDA. Unlike /search this DOES surface paperless (άυλη)
# prescriptions, so it is the resolve path the scan-barcode flow needs. We parse
# only the handful of fields downstream needs (plus the per-line therapy id +
# medicine barcode).
#
# PHI guard: the parsed object carries patient AMKA + name. Same contract as the
# /search dict — needed by the verification UI, never logged.


def _date_yyyymmdd(value: str | None) -> str | None:
    """``YYYYMMDD[HHMMSS]`` → ``YYYY-MM-DD``; None/unparseable → None."""
    if not value or len(value) < 8 or not value[:8].isdigit():
        return None
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _join_name(name_el: etree._Element | None) -> str | None:
    """Assemble ``<name><given/><family/></name>`` into "GIVEN FAMILY"."""
    if name_el is None:
        return None
    ns = {"hl7": NS_HL7}
    parts: list[str] = []
    for tag in ("given", "family"):
        for el in name_el.findall(f"hl7:{tag}", ns):
            if el.text and el.text.strip():
                parts.append(el.text.strip())
    return " ".join(parts) or None


@dataclass
class PrescriptionLine:
    """One prescribed medicine line from a retrieved prescription CDA."""

    line_id: str  # substanceAdministration/id[@root='1.21.1'] — the therapy-line id
    medicine_code: str  # manufacturedMaterial/code/@code (ΕΟΦ code)
    medicine_barcode: str  # narrative <item ID='med_barcode_N'> text (EAN/NHRN)
    medicine_name: str
    status: str  # substanceAdministration/statusCode/@code (e.g. "active")


@dataclass
class ParsedPrescription:
    """Parsed retrieval CDA — see ``parse_prescription_cda``."""

    barcode: str
    patient_amka: str | None
    patient_name: str | None
    physician: str | None
    issue_date: str | None
    expiry_date: str | None
    status: str | None
    lines: list[PrescriptionLine] = field(default_factory=list)

    def to_rx_dict(self, status_mapper=lambda s: s) -> dict:
        """Shape this into the SAME dict ``_parse_prescription_search_json``
        emits, so the safety engine and verification UI need no changes — plus
        a ``therapyLines`` list carrying the real per-line ids. ``status_mapper``
        is injected by the caller (pharmapi._map_pharmapi_status) to avoid a
        cda→pharmapi import cycle.

        Divergences from the /search-shaped dict (documented in
        docs/OPEN-ISSUES.md so a future caller doesn't expect them):

        * ``medication`` is the medicine NAME (str) here AND in the /search
          path; the mock fixtures embed a richer ``dict`` with ``nhrn``/etc.
        * ``socialInsurance``, ``repeatNo``, ``totalRepeats`` are intentionally
          ``None`` — the source CDA does not surface them. Extend the parser
          (and this dict) when a downstream feature depends on them.
        """
        first = self.lines[0] if self.lines else None
        return {
            "rxId": self.barcode,
            "patientName": self.patient_name or "Άγνωστος",
            "patientAmka": self.patient_amka,
            "medication": first.medicine_name if first else None,
            "medicineBarcode": first.medicine_barcode if first else None,
            "physician": self.physician,
            "date": self.issue_date,
            "expiryDate": self.expiry_date,
            "status": status_mapper(self.status),
            "socialInsurance": None,
            "pharmApiStatus": self.status,
            "repeatNo": None,
            "totalRepeats": None,
            "medicineDrug": False,
            "executions": None,
            "therapyLines": [
                {
                    "lineId": ln.line_id,
                    "medicineCode": ln.medicine_code,
                    "medicineBarcode": ln.medicine_barcode,
                    "name": ln.medicine_name,
                    "status": ln.status,
                }
                for ln in self.lines
            ],
        }


def parse_prescription_cda(xml_text: bytes | str) -> ParsedPrescription:
    """Parse a retrieved prescription CDA (Άντληση Συνταγής) into the fields the
    verification flow needs.

    Robust to multi-line prescriptions (one ``substanceAdministration`` per
    prescribed medicine). Element paths verified against a live testeps
    prescription; ids are read by ``@root`` so positional drift is irrelevant.
    """
    raw = xml_text if isinstance(xml_text, bytes) else xml_text.encode("utf-8")
    root = etree.fromstring(raw)
    ns = {"hl7": NS_HL7}

    bc_el = root.find(f"./hl7:id[@root='{ROOT_RX_BARCODE}']", ns)
    barcode = (bc_el.get("extension") if bc_el is not None else "") or ""

    patient_amka: str | None = None
    patient_name: str | None = None
    rt = root.find("./hl7:recordTarget", ns)
    if rt is not None:
        amka_el = rt.find(f".//hl7:id[@root='{ROOT_RECORD_TARGET_AMKA}']", ns)
        if amka_el is not None:
            patient_amka = amka_el.get("extension")
        patient_name = _join_name(rt.find(".//hl7:patient/hl7:name", ns))

    physician = _join_name(
        root.find("./hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name", ns)
    )

    # Narrative medicine barcodes: <text><list><item ID='med_barcode_N'>EAN</item>.
    narrative: dict[str, str] = {}
    for item in root.iter(f"{{{NS_HL7}}}item"):
        iid = item.get("ID") or ""
        if iid.startswith("med_barcode") and item.text and item.text.strip():
            narrative[iid] = item.text.strip()

    lines: list[PrescriptionLine] = []
    for sa in root.iter(f"{{{NS_HL7}}}substanceAdministration"):
        line_id_el = sa.find(f"hl7:id[@root='{ROOT_THERAPY_LINE}']", ns)
        line_id = (line_id_el.get("extension") if line_id_el is not None else "") or ""
        status_el = sa.find("hl7:statusCode", ns)
        status = (status_el.get("code") if status_el is not None else "") or ""
        med_code = med_name = med_barcode = ""
        mm = sa.find(".//hl7:manufacturedMaterial", ns)
        if mm is not None:
            code_el = mm.find("hl7:code", ns)
            if code_el is not None:
                med_code = code_el.get("code") or ""
                ref = code_el.find("hl7:originalText/hl7:reference", ns)
                if ref is not None and ref.get("value"):
                    med_barcode = narrative.get(ref.get("value").lstrip("#"), "")
            name_el = mm.find("hl7:name", ns)
            if name_el is not None and name_el.text:
                med_name = name_el.text.strip()
        lines.append(
            PrescriptionLine(
                line_id=line_id,
                medicine_code=med_code,
                medicine_barcode=med_barcode or med_code,  # fall back to ΕΟΦ code
                medicine_name=med_name,
                status=status,
            )
        )

    issue_date = expiry_date = None
    et = root.find(".//hl7:section/hl7:entry/hl7:act/hl7:effectiveTime", ns)
    if et is not None:
        low = et.find("hl7:low", ns)
        high = et.find("hl7:high", ns)
        issue_date = _date_yyyymmdd(low.get("value")) if low is not None else None
        expiry_date = _date_yyyymmdd(high.get("value")) if high is not None else None

    return ParsedPrescription(
        barcode=barcode,
        patient_amka=patient_amka,
        patient_name=patient_name,
        physician=physician,
        issue_date=issue_date,
        expiry_date=expiry_date,
        status=lines[0].status if lines else None,
        lines=lines,
    )
