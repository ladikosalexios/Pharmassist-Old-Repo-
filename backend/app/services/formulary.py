"""Formulary substitution — ranked therapeutic alternatives (BC-14).

Given a source drug (by barcode or ATC), returns alternatives in two tiers:

* ``generic_equivalent`` — same exact ATC level-5 code, same pharmaceutical
  form where both forms are known (a known-different form degrades the
  candidate to the class tier with a note).
* ``therapeutic_class`` — same ATC level-4 class prefix.

Filtered by ΕΟΠΥΥ coverage (``positiveList`` from masterdata — tri-state until
the first full sync after the BC-13 migration): ``strict`` keeps only known-
covered packs, ``lenient`` keeps known-covered + unknown and excludes only
known-uncovered. Inactive (out-of-circulation) packs are never returned.

Ranking inside a tier: known coverage first, then retail price ascending
(unknown prices last), then name. Dose notes compare parsed strengths and
always tell the pharmacist when a manual check is needed — this service
suggests, it never decides.
"""

import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog

TIER_GENERIC = "generic_equivalent"
TIER_CLASS = "therapeutic_class"

_COVERAGE_RANK = {True: 0, None: 1, False: 2}

# "500MG/TAB", "5 mg", "100MCG/DOSE", "250MG/5ML", "1%" — first value + unit,
# keeping a compound denominator when present so 250MG/5ML ≠ 250MG/TAB.
_STRENGTH_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*((?:MG|MCG|UG|G|IU|ML|%)(?:/\d*(?:MG|MCG|G|ML|TAB|CAP|DOSE|VIAL)?)?)",
    re.IGNORECASE,
)


def parse_strength(text: str | None) -> tuple[Decimal | None, str | None]:
    """Best-effort (value, unit) from a masterdata `content` string.

    Returns (None, None) when unparseable — callers must treat that as
    "manual dose check", never as equality.
    """
    if not text:
        return None, None
    match = _STRENGTH_RE.search(text)
    if not match:
        return None, None
    raw_value, raw_unit = match.groups()
    try:
        value = Decimal(raw_value.replace(",", "."))
    except InvalidOperation:
        return None, None
    return value, raw_unit.upper().replace(" ", "")


def _strength_of(row: DrugCatalog) -> tuple[Decimal | None, str | None]:
    if row.strength_value is not None and row.strength_unit:
        return row.strength_value, row.strength_unit
    # Fall back to parsing whatever text we have — strength_raw for synced
    # rows, the brand+strength concat in name_gr for legacy/seed rows.
    return parse_strength(row.strength_raw or row.name_gr)


def dose_note(source: DrugCatalog | None, candidate: DrugCatalog) -> str:
    """Human dose-conversion note; never silently claims equivalence."""
    if source is None:
        return "No source strength to compare — verify dose manually"
    src_value, src_unit = _strength_of(source)
    cand_value, cand_unit = _strength_of(candidate)
    if src_value is None or cand_value is None:
        return "Strength unparseable — verify dose manually"
    if src_unit != cand_unit:
        return (
            f"Different strength units ({src_value}{src_unit} → {cand_value}{cand_unit}) "
            "— verify dose conversion manually"
        )
    if src_value == cand_value:
        return f"Same strength ({src_value}{src_unit})"
    return (
        f"Strength differs: {src_value}{src_unit} → {cand_value}{cand_unit} "
        "— verify dose conversion"
    )


def _passes_coverage(row: DrugCatalog, coverage_filter: str) -> bool:
    if coverage_filter == "strict":
        return row.eopyy_coverage is True
    return row.eopyy_coverage is not False  # lenient: covered or unknown


def rank_alternatives(
    source: DrugCatalog | None,
    source_atc: str,
    candidates: list[DrugCatalog],
    coverage_filter: str = "lenient",
) -> list[dict]:
    """Pure ranking over already-fetched candidate rows (unit-testable).

    Returns dicts: {row, tier, dose_note} sorted best-first. ``source`` may be
    None when the caller substitutes by ATC only (no source pack to compare
    form/strength against).
    """
    source_form = source.form_code if source is not None else None
    ranked: list[tuple[tuple, dict]] = []
    for row in candidates:
        if not row.active or not row.atc_code:
            continue
        if source is not None and row.gns_code == source.gns_code:
            continue
        if not _passes_coverage(row, coverage_filter):
            continue

        note = dose_note(source, row)
        if row.atc_code == source_atc:
            forms_known = bool(source_form) and bool(row.form_code)
            if forms_known and row.form_code != source_form:
                tier = TIER_CLASS
                note = f"Different pharmaceutical form ({source_form} → {row.form_code}); {note}"
            else:
                tier = TIER_GENERIC
                if not forms_known:
                    note = f"{note}; form not recorded — confirm same form"
        else:
            tier = TIER_CLASS

        tier_order = 0 if tier == TIER_GENERIC else 1
        price = row.retail_price if row.retail_price is not None else Decimal("Infinity")
        sort_key = (tier_order, _COVERAGE_RANK[row.eopyy_coverage], price, row.name_gr)
        ranked.append((sort_key, {"row": row, "tier": tier, "dose_note": note}))

    ranked.sort(key=lambda pair: pair[0])
    return [entry for _, entry in ranked]


async def alternatives(
    session: AsyncSession,
    *,
    barcode: str | None = None,
    atc: str | None = None,
    coverage_filter: str = "lenient",
    limit: int = 10,
) -> dict | None:
    """Ranked alternatives for a drug. Returns None when `barcode` is unknown.

    Same-class candidates are pulled by ATC level-4 prefix (index-backed since
    BC-13). The response carries ``data_caveats`` so callers see exactly where
    the catalogue data is incomplete rather than trusting silence.
    """
    source: DrugCatalog | None = None
    if barcode:
        source = (
            await session.scalars(select(DrugCatalog).where(DrugCatalog.gns_code == barcode))
        ).one_or_none()
        if source is None:
            return None
        source_atc = source.atc_code
    else:
        source_atc = (atc or "").strip().upper()

    caveats: list[str] = []
    if not source_atc:
        caveats.append("Source drug has no ATC code recorded — cannot search alternatives")
        return {
            "source": source,
            "source_atc": source_atc,
            "alternatives": [],
            "data_caveats": caveats,
        }

    atc4 = source_atc[:5]  # ATC level 4 = first 5 characters (e.g. B01AA)
    conds = [DrugCatalog.atc_code.like(f"{atc4}%"), DrugCatalog.active.is_(True)]
    if barcode:
        conds.append(DrugCatalog.gns_code != barcode)
    rows = list(await session.scalars(select(DrugCatalog).where(*conds)))
    ranked = rank_alternatives(source, source_atc, rows, coverage_filter)

    unknown_coverage = sum(1 for entry in ranked if entry["row"].eopyy_coverage is None)
    if unknown_coverage:
        caveats.append(
            f"ΕΟΠΥΥ coverage unknown for {unknown_coverage} candidate(s) — "
            "run the masterdata sync to backfill (positiveList)"
        )
    if source is not None and not source.form_code:
        caveats.append("Source pharmaceutical form not recorded — form match not enforced")

    return {
        "source": source,
        "source_atc": source_atc,
        "alternatives": ranked[:limit],
        "data_caveats": caveats,
    }
