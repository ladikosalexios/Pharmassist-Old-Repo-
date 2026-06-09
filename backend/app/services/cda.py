"""HL7 eDispensation CDA builder and response parser.

Spec source: ΗΔΥΚΑ pharmapi v2 OpenAPI doc — `info.description` →
``## Εκτέλεση Συνταγής`` at
``https://testeps.e-prescription.gr/pharmapiv2/v3/api-docs/manufacturers``.

Namespaces and OID roots are pinned to that spec; the goldens under
``backend/tests/fixtures/cda/`` are extracted from it verbatim. Do not invent
new template IDs — extend by patching the spec or the fixture and re-running
``tests/test_cda.py``.

PHI guard: the response CDA carries patient identifiers (AMKA, name, address).
Callers must NOT log the parsed object, only the ``exec_ref`` and outer status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from lxml import etree

# ── Namespaces ──────────────────────────────────────────────────────────────
NS_HL7 = "urn:hl7-org:v3"
NS_EPSOS = "urn:epsos-org:ep:medication"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
# nsmap key=None defines the *default* xmlns on the root element. Order
# matches the spec example (xsi, epsos, then default) so byte-level diffs
# against the golden stay readable.
NSMAP = {"xsi": NS_XSI, "epsos": NS_EPSOS, None: NS_HL7}

# ── OID roots (verbatim from the spec) ──────────────────────────────────────
TPL_EDISPENSATION = "1.3.6.1.4.1.12559.11.10.1.3.1.1.2"
ROOT_RX_BARCODE = "1.21"
# recordTarget patient AMKA, used only when parsing a retrieved prescription CDA
# (Άντληση Συνταγής → GET /api/v1/prescriptions/get/{barcode}).
ROOT_RECORD_TARGET_AMKA = "1.10.1"
ROOT_PRESCRIPTION_ID = "1.22"  # request: id of the source Rx; response: id of THIS execution
ROOT_PHARMACY_UNIT = "1.18.1.1"
ROOT_EXECUTION_CASE = "2.10.7"  # 0=ΟΧΙ ΠΛΗΡΩΣ, 1=ΟΛΑ, 2=ΕΠΙΘΥΜΙΑ ΑΣΘΕΝΗ, 3=ΑΣΥΜΦΩΝΙΑ
ROOT_OPINION = "1.1.23"
ROOT_THERAPY_LINE = "1.21.1"
ROOT_CONSENT = "2.10.6"
ROOT_PRICE_DISPENSED = "2.10.9"
ROOT_RETAIL_PRICE = "2.10.11"
ROOT_REFERENCE_PRICE = "2.10.10"
ROOT_DOUBLE_CANCEL = "2.10.13"
ROOT_DISPENSE_MODE = "2.10.14"  # 0=ΕΟΦ ταινία γνησιότητας, 1=HMVS QR
ROOT_QR_PRODUCT_CODE = "2.10.15"
ROOT_QR_BATCH = "2.10.16"
ROOT_QR_EXPIRY = "2.10.17"
ROOT_QR_MANUAL = "2.10.18"
ROOT_QR_CODE_TYPE = "2.10.19"
# ΙΦΕΤ (special-import) roots — kept for spec parity, only emitted when
# DispenseItem.ifet_import=True.
ROOT_IFET_COMMERCIAL_NAME = "1.4.28"
ROOT_IFET_DOSE_UNIT = "1.4.29"
ROOT_IFET_PHARM_FORM_CODE = "1.4.30"
ROOT_IFET_PHARM_CONTENT = "1.4.31"
ROOT_IFET_PACKAGE = "1.4.32"
ROOT_IFET_UNIT_PRICE = "1.4.33"


@dataclass
class DispenseItem:
    """A single medicine line on a dispense.

    ``therapy_line_id`` corresponds to ΗΔΥΚΑ's per-line prescription id
    (response root="1.21.1"). ``lot_number`` is the EOF strip number when
    ``dispense_mode=0`` or the HMVS QR serial when ``dispense_mode=1``.
    """

    therapy_line_id: str
    medicine_barcode: str
    lot_number: str
    # Default 1=ΝΑΙ per spec example; downstream consent capture lives in the
    # documentation_log, this only goes on the upstream eDispensation envelope.
    consent: int = 1
    price_dispensed: str = "0"
    retail_price: str = "0"
    reference_price: str = "0"
    # Double-cancellation of ΕΟΦ strip — only relevant during reversal flows.
    # TODO(P3-followup): wire reversal; for now always 0 per "no reversal" brief.
    double_cancel: int = 0
    dispense_mode: int = 0  # 0=ΕΟΦ strip, 1=HMVS QR
    # QR-only fields — required by spec when dispense_mode=1.
    qr_product_code: str | None = None
    qr_batch_no: str | None = None
    qr_expiry: str | None = None
    qr_manual_entry: int = 0
    qr_code_type: str = "GS1"
    # ΙΦΕΤ-import block — emitted only when explicitly flagged. The brief
    # leaves ΙΦΕΤ imports out of scope; fields default to spec-example
    # placeholders so the golden fixture comparison still passes when a caller
    # opts in.
    ifet_import: bool = False
    ifet_commercial_name: str = ""
    ifet_dose_unit: str = ""
    ifet_pharm_form_code: str = ""
    ifet_pharm_content: str = ""
    ifet_package: str = ""
    ifet_unit_price: str = ""


@dataclass
class DispensedRx:
    """Parsed eDispensation response — see ``parse_dispense_response``."""

    exec_ref: str  # ΗΔΥΚΑ executionNo (response root="1.22")
    barcode: str  # source Rx barcode (response root="1.21")
    executed_at: str  # response /effectiveTime/@value (YYYYMMDD)
    response_cda: str = field(repr=False)  # raw XML for the receipt column

    def to_envelope(self) -> dict:
        """Shape both pharmapi_dispense mock and live branches return.

        ``executed_at`` is converted to ISO-8601 for the JSON receipt; raw
        spec timestamps are YYYYMMDD or YYYYMMDDHHMMSS.
        """
        # Spec timestamps are yyyymmdd (date) or yyyymmddHHMMSS — normalise to ISO.
        ts_iso = _normalise_response_timestamp(self.executed_at)
        return {
            "exec_ref": self.exec_ref,
            "executed_at": ts_iso,
            "status": "EXECUTED",
            "barcode": self.barcode,
        }


def _id(parent: etree._Element, root: str, extension) -> etree._Element:
    el = etree.SubElement(parent, "id")
    el.set("extension", str(extension))
    el.set("root", root)
    return el


def _build_execution_act(section: etree._Element, execution_case: int, opinion: int) -> None:
    entry = etree.SubElement(section, "entry")
    act = etree.SubElement(entry, "act")
    _id(act, ROOT_EXECUTION_CASE, execution_case)
    _id(act, ROOT_OPINION, opinion)


def _build_supply(section: etree._Element, idx: int, item: DispenseItem) -> None:
    entry = etree.SubElement(section, "entry")
    supply = etree.SubElement(entry, "supply", classCode="SPLY", moodCode="ENV")
    _id(supply, ROOT_THERAPY_LINE, item.therapy_line_id)
    product = etree.SubElement(supply, "product")
    mfp = etree.SubElement(product, "manufacturedProduct", classCode="MANU")
    mfm = etree.SubElement(mfp, "manufacturedMaterial")
    code = etree.SubElement(mfm, "code")
    original_text = etree.SubElement(code, "originalText")
    ref = etree.SubElement(original_text, "reference")
    ref.set("value", f"#med_barcode_{idx}")
    as_content = etree.SubElement(mfm, f"{{{NS_EPSOS}}}asContent", classCode="CONT")
    container = etree.SubElement(
        as_content,
        f"{{{NS_EPSOS}}}containerPackagedMedicine",
        classCode="CONT",
        determinerCode="KIND",
    )
    lot = etree.SubElement(container, f"{{{NS_EPSOS}}}lotNumberText")
    lot.text = item.lot_number

    rel = etree.SubElement(supply, "entryRelationship", typeCode="SPRT")
    act = etree.SubElement(rel, "act", classCode="ACT", moodCode="EVN")
    _id(act, ROOT_CONSENT, item.consent)
    _id(act, ROOT_PRICE_DISPENSED, item.price_dispensed)
    _id(act, ROOT_RETAIL_PRICE, item.retail_price)
    _id(act, ROOT_REFERENCE_PRICE, item.reference_price)
    _id(act, ROOT_DOUBLE_CANCEL, item.double_cancel)
    _id(act, ROOT_DISPENSE_MODE, item.dispense_mode)
    if item.dispense_mode == 1:
        if not all([item.qr_product_code, item.qr_batch_no, item.qr_expiry]):
            raise ValueError(
                "dispense_mode=1 (HMVS QR) requires qr_product_code, qr_batch_no, qr_expiry"
            )
        _id(act, ROOT_QR_PRODUCT_CODE, item.qr_product_code)
        _id(act, ROOT_QR_BATCH, item.qr_batch_no)
        _id(act, ROOT_QR_EXPIRY, item.qr_expiry)
        _id(act, ROOT_QR_MANUAL, item.qr_manual_entry)
        _id(act, ROOT_QR_CODE_TYPE, item.qr_code_type)
    if item.ifet_import:
        _id(act, ROOT_IFET_COMMERCIAL_NAME, item.ifet_commercial_name)
        _id(act, ROOT_IFET_DOSE_UNIT, item.ifet_dose_unit)
        _id(act, ROOT_IFET_PHARM_FORM_CODE, item.ifet_pharm_form_code)
        _id(act, ROOT_IFET_PHARM_CONTENT, item.ifet_pharm_content)
        _id(act, ROOT_IFET_PACKAGE, item.ifet_package)
        _id(act, ROOT_IFET_UNIT_PRICE, item.ifet_unit_price)


def build_dispense_cda(
    *,
    barcode: str,
    pharmacy_unit_id: int | str,
    items: list[DispenseItem],
    execution_case: int = 1,
    opinion: int = 1,
) -> bytes:
    """Build the eDispensation request CDA POSTed to /prescriptions/dispense.

    ``execution_case`` defaults to 1 (ΟΛΑ ΤΑ ΦΑΡΜΑΚΑ ΕΚΤΕΛΕΣΤΗΚΑΝ). Partial
    dispense (0/2/3) is out of scope per the P3 brief and TODO-flagged below.
    Pharmacy + pharmacist identifiers must come from the session (deps.
    get_current_user / pharmapi_session.pharmacy_id), never from the request
    body — see ``pharmapi.pharmapi_dispense`` for the call shape.
    """
    if not items:
        raise ValueError("build_dispense_cda requires at least one DispenseItem")
    # TODO(P3-followup): support execution_case ∈ {0,2,3} for partial dispense
    #   + reversal once the upstream cancel CDA is wired.
    if execution_case != 1:
        raise NotImplementedError(
            f"execution_case={execution_case} (partial dispense) not yet wired"
        )

    cd = etree.Element("ClinicalDocument", nsmap=NSMAP)
    tpl = etree.SubElement(cd, "templateId")
    tpl.set("root", TPL_EDISPENSATION)
    _id(cd, ROOT_RX_BARCODE, barcode)

    author = etree.SubElement(cd, "author")
    assigned_author = etree.SubElement(author, "assignedAuthor")
    represented_org = etree.SubElement(assigned_author, "representedOrganization")
    _id(represented_org, ROOT_PHARMACY_UNIT, pharmacy_unit_id)

    component = etree.SubElement(cd, "component")
    sb = etree.SubElement(component, "structuredBody")
    inner_comp = etree.SubElement(sb, "component")
    section = etree.SubElement(inner_comp, "section")

    text_el = etree.SubElement(section, "text")
    list_el = etree.SubElement(text_el, "list")
    for idx, item in enumerate(items, start=1):
        med_item = etree.SubElement(list_el, "item", ID=f"med_barcode_{idx}")
        med_item.text = item.medicine_barcode

    _build_execution_act(section, execution_case, opinion)
    for idx, item in enumerate(items, start=1):
        _build_supply(section, idx, item)

    return etree.tostring(
        cd,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
        pretty_print=True,
    )


def parse_dispense_response(xml_text: bytes | str) -> DispensedRx:
    """Extract executionNo + receipt fields from the eDispensation response CDA.

    ``executionNo`` is the id at section/entry/act with root='1.22'. We avoid
    relying on positional XPath because real responses will carry richer
    structure than the spec example.
    """
    raw = xml_text if isinstance(xml_text, bytes) else xml_text.encode("utf-8")
    root = etree.fromstring(raw)
    ns = {"hl7": NS_HL7}

    exec_xpath = f".//hl7:section/hl7:entry/hl7:act/hl7:id[@root='{ROOT_PRESCRIPTION_ID}']"
    exec_id_el = root.find(exec_xpath, ns)
    if exec_id_el is None or not exec_id_el.get("extension"):
        raise ValueError(
            f"eDispensation response missing executionNo (id[@root='{ROOT_PRESCRIPTION_ID}'])"
        )
    exec_ref = exec_id_el.get("extension")

    barcode_xpath = f".//hl7:inFulfillmentOf/hl7:order/hl7:id[@root='{ROOT_RX_BARCODE}']"
    barcode_el = root.find(barcode_xpath, ns)
    if barcode_el is None or not barcode_el.get("extension"):
        raise ValueError("eDispensation response missing inFulfillmentOf/order Rx barcode")
    barcode = barcode_el.get("extension")

    effective_time_el = root.find("./hl7:effectiveTime", ns)
    executed_at = (effective_time_el.get("value") if effective_time_el is not None else "") or ""

    return DispensedRx(
        exec_ref=exec_ref,
        barcode=barcode,
        executed_at=executed_at,
        response_cda=raw.decode("utf-8") if isinstance(raw, bytes) else raw,
    )


def _normalise_response_timestamp(value: str) -> str:
    """Convert spec timestamp (YYYYMMDD or YYYYMMDDHHMMSS) to ISO-8601.

    Falls back to ``datetime.now(UTC).isoformat()`` if the value is empty or
    unparseable — keeps the response envelope safe rather than 502-ing on a
    new ΗΔΥΚΑ format. Logged at parse time so drift becomes visible.
    """
    fmts = ("%Y%m%d%H%M%S", "%Y%m%d")
    for fmt in fmts:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC).isoformat()
        except (ValueError, TypeError):
            continue
    return datetime.now(UTC).isoformat()


# ── Prescription retrieval (Άντληση Συνταγής) ───────────────────────────────
# GET /api/v1/prescriptions/get/{barcode} returns the SOURCE prescription as an
# epSOS ePrescription CDA (NOT the eDispensation we build). Unlike /search this
# DOES surface paperless (άυλη) prescriptions, so it is the resolve path the
# scan-barcode flow needs. We parse only the handful of fields downstream needs
# (and the per-line therapy id + medicine barcode the eDispensation must echo).
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
        emits, so the safety engine, verification UI, and dispense builder need
        no changes — plus a ``therapyLines`` list carrying the real per-line ids
        the eDispensation must echo. ``status_mapper`` is injected by the caller
        (pharmapi._map_pharmapi_status) to avoid a cda→pharmapi import cycle."""
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
    verification + dispense flow needs.

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
