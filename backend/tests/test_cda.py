"""Golden-file tests for app.services.cda.

The fixtures under ``tests/fixtures/cda/`` are extracted verbatim from the
ΗΔΥΚΑ pharmapi v2 spec's ``## Εκτέλεση Συνταγής`` section. Comparison is
semantic (XML element tree) so cosmetic whitespace / inline-comment drift
between lxml output and the spec doesn't fail the run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from app.services.cda import (
    DispenseItem,
    build_dispense_cda,
    parse_dispense_response,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cda"
REQUEST_GOLDEN = FIXTURES / "dispense_request_sample.xml"
RESPONSE_GOLDEN = FIXTURES / "dispense_response_sample.xml"


def _parse_clean(xml: bytes | str) -> etree._Element:
    parser = etree.XMLParser(remove_comments=True, remove_blank_text=True)
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    return etree.fromstring(xml, parser)


def _compare(a: etree._Element, b: etree._Element, path: str = "/") -> None:
    here = f"{path}{etree.QName(a.tag).localname}"
    assert a.tag == b.tag, f"tag differs at {here}: {a.tag} vs {b.tag}"
    assert dict(a.attrib) == dict(b.attrib), (
        f"attrib differs at {here}: {dict(a.attrib)} vs {dict(b.attrib)}"
    )
    ta = (a.text or "").strip()
    tb = (b.text or "").strip()
    assert ta == tb, f"text differs at {here}: {ta!r} vs {tb!r}"
    ca, cb = list(a), list(b)
    assert len(ca) == len(cb), (
        f"child count differs at {here}: {len(ca)} (built) vs {len(cb)} (golden)"
    )
    for i, (x, y) in enumerate(zip(ca, cb, strict=True)):
        _compare(x, y, f"{here}[{i}]/")


def _canonical_items() -> list[DispenseItem]:
    """The two-medicine example from the spec — first row uses ΕΟΦ strip mode
    and includes the ΙΦΕΤ-import block; second uses HMVS QR mode without ΙΦΕΤ.
    """
    return [
        DispenseItem(
            therapy_line_id="22033332",
            medicine_barcode="2802676702022",
            lot_number="230100011999",
            consent=1,
            price_dispensed="10",
            retail_price="10",
            reference_price="25",
            double_cancel=0,
            dispense_mode=0,
            ifet_import=True,
            ifet_commercial_name="commercial name",
            ifet_dose_unit="dose unit",
            ifet_pharm_form_code="pharm form code",
            ifet_pharm_content="pharm content",
            ifet_package="package",
            ifet_unit_price="10.0",
        ),
        DispenseItem(
            therapy_line_id="22033333",
            medicine_barcode="2802009201024",
            lot_number="123BDF2123",
            consent=1,
            price_dispensed="10",
            retail_price="10",
            reference_price="25",
            double_cancel=0,
            dispense_mode=1,
            qr_product_code="123A2123",
            qr_batch_no="123A2123",
            qr_expiry="241212",
            qr_manual_entry=0,
            qr_code_type="GS1",
        ),
    ]


def test_request_matches_spec_golden() -> None:
    built = build_dispense_cda(
        barcode="2411223344556",
        pharmacy_unit_id=6543,
        items=_canonical_items(),
        execution_case=1,
        opinion=1,
    )
    golden = REQUEST_GOLDEN.read_bytes()
    _compare(_parse_clean(built), _parse_clean(golden))


def test_request_requires_at_least_one_item() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_dispense_cda(barcode="X", pharmacy_unit_id=1, items=[])


def test_request_partial_dispense_not_yet_wired() -> None:
    with pytest.raises(NotImplementedError, match="execution_case=0"):
        build_dispense_cda(
            barcode="X",
            pharmacy_unit_id=1,
            items=_canonical_items()[:1],
            execution_case=0,
        )


def test_request_qr_mode_requires_qr_fields() -> None:
    with pytest.raises(ValueError, match="HMVS QR"):
        build_dispense_cda(
            barcode="X",
            pharmacy_unit_id=1,
            items=[
                DispenseItem(
                    therapy_line_id="L1",
                    medicine_barcode="B1",
                    lot_number="LOT1",
                    dispense_mode=1,  # missing qr_*
                )
            ],
        )


def test_parse_response_golden() -> None:
    parsed = parse_dispense_response(RESPONSE_GOLDEN.read_bytes())
    assert parsed.exec_ref == "22033332"
    assert parsed.barcode == "2411223344556"
    assert parsed.executed_at == "20241119"

    envelope = parsed.to_envelope()
    assert envelope["status"] == "EXECUTED"
    assert envelope["exec_ref"] == "22033332"
    assert envelope["barcode"] == "2411223344556"
    # Timestamp normalised to ISO with UTC zone.
    assert envelope["executed_at"].startswith("2024-11-19T00:00:00")
    assert envelope["executed_at"].endswith("+00:00")


def test_parse_response_missing_exec_ref_raises() -> None:
    bad = b"<ClinicalDocument xmlns='urn:hl7-org:v3'/>"
    with pytest.raises(ValueError, match="executionNo"):
        parse_dispense_response(bad)
