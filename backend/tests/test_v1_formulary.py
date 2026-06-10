"""BC-14 formulary unit tests — strength parsing, tiering, coverage filters,
ranking, dose notes. Pure in-memory DrugCatalog rows; no DB."""

import base64
import os

os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

from decimal import Decimal  # noqa: E402

from app.db.models.drug_catalog import DrugCatalog  # noqa: E402
from app.services.formulary import (  # noqa: E402
    TIER_CLASS,
    TIER_GENERIC,
    dose_note,
    parse_strength,
    rank_alternatives,
)


def _drug(
    barcode: str,
    atc: str,
    name: str,
    *,
    form: str | None = "TAB",
    strength: str | None = None,
    value=None,
    unit: str | None = None,
    coverage: bool | None = True,
    price=None,
    active: bool = True,
) -> DrugCatalog:
    return DrugCatalog(
        gns_code=barcode,
        atc_code=atc,
        atc_class="",
        name_gr=name,
        name_en=None,
        active=active,
        form_code=form,
        strength_raw=strength,
        strength_value=Decimal(str(value)) if value is not None else None,
        strength_unit=unit,
        retail_price=Decimal(str(price)) if price is not None else None,
        eopyy_coverage=coverage,
    )


SOURCE = _drug("100", "B01AA03", "Warfarin", strength="5MG/TAB", value=5, unit="MG")


# ── parse_strength ───────────────────────────────────────────────────────────


def test_parse_strength_simple_and_compound():
    assert parse_strength("500MG/TAB") == (Decimal("500"), "MG/TAB")
    assert parse_strength("5 mg") == (Decimal("5"), "MG")
    assert parse_strength("250MG/5ML") == (Decimal("250"), "MG/5ML")
    assert parse_strength("1%") == (Decimal("1"), "%")
    assert parse_strength("2,5MG/TAB") == (Decimal("2.5"), "MG/TAB")


def test_parse_strength_unparseable():
    assert parse_strength(None) == (None, None)
    assert parse_strength("") == (None, None)
    assert parse_strength("χωρίς δοσολογία") == (None, None)


# ── Tiering ──────────────────────────────────────────────────────────────────


def test_same_atc_same_form_is_generic_equivalent():
    cand = _drug("101", "B01AA03", "Warfarin Generic", value=5, unit="MG")
    ranked = rank_alternatives(SOURCE, "B01AA03", [cand])
    assert ranked[0]["tier"] == TIER_GENERIC
    assert "Same strength" in ranked[0]["dose_note"]


def test_same_atc_different_form_degrades_to_class_tier():
    cand = _drug("102", "B01AA03", "Warfarin Syrup", form="SYR", value=5, unit="MG")
    ranked = rank_alternatives(SOURCE, "B01AA03", [cand])
    assert ranked[0]["tier"] == TIER_CLASS
    assert "Different pharmaceutical form" in ranked[0]["dose_note"]


def test_same_class_different_molecule_is_class_tier():
    cand = _drug("103", "B01AA07", "Acenocoumarol", value=4, unit="MG")
    ranked = rank_alternatives(SOURCE, "B01AA03", [cand])
    assert ranked[0]["tier"] == TIER_CLASS


def test_source_itself_and_inactive_rows_are_excluded():
    inactive = _drug("104", "B01AA03", "Withdrawn", active=False)
    ranked = rank_alternatives(SOURCE, "B01AA03", [SOURCE, inactive])
    assert ranked == []


# ── Coverage filter (tri-state) ──────────────────────────────────────────────


def test_lenient_keeps_unknown_excludes_uncovered():
    covered = _drug("105", "B01AA03", "Covered", coverage=True)
    unknown = _drug("106", "B01AA03", "Unknown", coverage=None)
    uncovered = _drug("107", "B01AA03", "Uncovered", coverage=False)
    ranked = rank_alternatives(SOURCE, "B01AA03", [covered, unknown, uncovered], "lenient")
    names = [entry["row"].name_gr for entry in ranked]
    assert names == ["Covered", "Unknown"]  # covered ranks before unknown


def test_strict_keeps_only_known_covered():
    covered = _drug("105", "B01AA03", "Covered", coverage=True)
    unknown = _drug("106", "B01AA03", "Unknown", coverage=None)
    ranked = rank_alternatives(SOURCE, "B01AA03", [unknown, covered], "strict")
    assert [entry["row"].name_gr for entry in ranked] == ["Covered"]


# ── Ranking ──────────────────────────────────────────────────────────────────


def test_generic_tier_ranks_before_class_and_cheaper_first():
    generic_cheap = _drug("110", "B01AA03", "Gen Cheap", value=5, unit="MG", price=2)
    generic_dear = _drug("111", "B01AA03", "Gen Dear", value=5, unit="MG", price=9)
    generic_no_price = _drug("112", "B01AA03", "Gen NoPrice", value=5, unit="MG")
    class_alt = _drug("113", "B01AA07", "Aceno", value=4, unit="MG", price=1)
    ranked = rank_alternatives(
        SOURCE, "B01AA03", [class_alt, generic_no_price, generic_dear, generic_cheap]
    )
    assert [entry["row"].name_gr for entry in ranked] == [
        "Gen Cheap",
        "Gen Dear",
        "Gen NoPrice",  # unknown price ranks last within the tier
        "Aceno",  # class tier after every generic, despite the lowest price
    ]


# ── Dose notes ───────────────────────────────────────────────────────────────


def test_dose_note_flags_strength_difference_and_unit_mismatch():
    differs = _drug("120", "B01AA03", "W3", value=3, unit="MG")
    assert "5MG → 3MG" in dose_note(SOURCE, differs).replace(" ", "")[:30] or "3MG" in dose_note(
        SOURCE, differs
    )
    other_unit = _drug("121", "B01AA03", "Wmcg", value=500, unit="MCG")
    assert "unit" in dose_note(SOURCE, other_unit).lower()


def test_dose_note_never_claims_equivalence_when_unparseable():
    mystery = _drug("122", "B01AA03", "Mystery")
    note = dose_note(SOURCE, mystery)
    assert "manual" in note.lower()
    assert "same strength" not in note.lower()


def test_dose_note_falls_back_to_parsing_name_text():
    # Legacy/seed rows carry strength only inside the name text — same value
    # AND unit as the source so the fallback parse proves equivalence.
    legacy = _drug("123", "B01AA03", "Warfarin 5 MG", strength=None)
    assert "Same strength" in dose_note(SOURCE, legacy)
