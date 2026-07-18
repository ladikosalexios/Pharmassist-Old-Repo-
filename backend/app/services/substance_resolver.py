"""activeSubstance / commercialName → ATC resolution seam.

Two live-mode gaps in the safety engine need a drug **name** (or substance code)
mapped to an **ATC code** before the deterministic rule engine can use it:

* Patient **intolerances** come back from ΗΔΥΚΑ carrying ``activeSubstance``
  (an INN description, sometimes a ``{code, description}`` object) and a type —
  but no ATC. Without the ATC the engine can't match them against a dispensed
  drug (``safety_engine.py`` §2).
* Patient **medicine history** (co-medication) comes back with
  ``medicineCommercialName`` and no medicine barcode, so the barcode→ATC path
  (``drug_catalog.atc_codes_for_barcodes``) can't be used and interaction checks
  never fire in live mode (``safety_engine.py`` §1).

This module is the single seam both paths call. Today it resolves
**deterministically** against ``drug_catalog`` — which already stores, per row,
the main ``substance_code``, the INN ``name_en``, the brand ``name_gr``, and the
``atc_code``. Resolution walks three passes, most-confident first:

1. ``substance_code`` exact  → high confidence
2. INN ``name_en`` exact (case-insensitive) → high confidence
3. brand ``name_gr`` substring, **unambiguous only** → low confidence

Every pass keeps a mapping ONLY when the matched catalog rows agree on a single
ATC; an ambiguous match resolves to ``None`` (the caller then skips it) so the
engine never invents a false interaction from a fuzzy brand hit.

── AI-driven later (the seam this is shaped for) ──────────────────────────────
The engine is Tier-1 deterministic and MUST NOT import the LLM seam
(``services/llm.py`` — enforced by ``tests/test_no_tier1_llm_import.py``). So the
future AI resolver does **not** run inside ``evaluate_safety``. Instead it runs
**offline over the catalog misses** — an opt-in/background job that asks the LLM
to map an unresolved name→ATC (messy brand spellings, combination products,
foreign names the deterministic passes can't catch) and writes the result to a
persistent map (a ``substance_atc_map`` table, or reusing ``ai_response_cache``).
``resolve_atcs`` then reads that map as a fourth deterministic pass. The engine
never changes and never imports the LLM — exactly how ``drug_catalog`` sync
enriches the catalog out-of-band while the request path only reads.

The ``ResolvedAtc.method``/``confidence`` fields exist so that when the AI pass
lands, a resolution's provenance ("inn_name" vs "ai") and confidence are already
first-class — a caller (or an audit view) can treat a low-confidence AI mapping
differently without a shape change here.
"""

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog


@dataclass(frozen=True)
class DrugHint:
    """What we know about a drug that needs an ATC. Any subset may be populated;
    ``raw`` is the original upstream value, kept for logging and as the input the
    future AI pass would receive for a catalog miss."""

    substance_code: str | None = None
    substance_name: str | None = None  # INN / activeSubstance description
    commercial_name: str | None = None  # brand (e.g. ΗΔΥΚΑ medicineCommercialName)
    raw: str | None = None


@dataclass(frozen=True)
class ResolvedAtc:
    atc_code: str
    method: str  # "substance_code" | "inn_name" | "commercial_name" | (future) "ai"
    confidence: str  # "high" | "low"
    # The catalog row carries these alongside the ATC — projected so a single
    # resolution yields the comparison key (substance_code, the exact generic-
    # equivalence id) AND the INN keyword (§4.5) without a second round-trip.
    substance_code: str | None = None
    inn_name: str | None = None


# One catalog row's resolvable identity: (atc, substance_code, inn_name).
_Rec = tuple[str, str | None, str | None]


def _pick_unambiguous(rows: list[tuple[str, str, str | None, str | None]]) -> dict[str, _Rec]:
    """Group (key, atc, substance_code, inn) rows and keep a key only when its
    rows agree on ONE ATC — the kept record carries that ATC plus the first
    non-blank substance_code / INN seen.

    Two brands/strengths of the same substance share an ATC (kept); a key that
    maps to two distinct ATCs (an ambiguous brand) is dropped rather than guessed
    — a false interaction is worse than a missed one here."""
    groups: dict[str, dict] = {}
    for key, atc, sub, inn in rows:
        if not atc:
            continue
        g = groups.setdefault(key, {"atcs": set(), "atc": atc, "sub": None, "inn": None})
        g["atcs"].add(atc)
        if g["sub"] is None and sub:
            g["sub"] = sub
        if g["inn"] is None and inn:
            g["inn"] = inn
    return {k: (g["atc"], g["sub"], g["inn"]) for k, g in groups.items() if len(g["atcs"]) == 1}


# ── Brand-name normalisation ──────────────────────────────────────────────────
# ΗΔΥΚΑ history brands ("OLENXA DISP.TAB 20MG/TAB BTx28") carry form/strength/pack
# noise that drifts from the catalog's name_gr formatting, so the old full-string
# substring match missed often. Every strength/pack of a brand shares ONE ATC +
# substance, so we key on the leading BRAND tokens (stop at the first form /
# strength / pack token) and prefix-match name_gr — far more robust, still
# unambiguous-only (different brands sharing a prefix → multiple ATCs → dropped).
_FORM_OR_STRENGTH = re.compile(
    r"^(?:\d|TABS?|CAPS?|F\.?C|DISP|SR|MR|SYR|SOL|SUSP|INJ|CREAM|GEL|OINT|"
    r"DROPS?|AMP|VIAL|SACHET|EFF|BT|BTX|MG|G|ML|MCG|IU|%)",
    re.IGNORECASE,
)


def _brand_key(name: str) -> str:
    """Leading brand tokens of a commercial name, uppercased — everything up to
    the first form/strength/pack token. Splits on whitespace only (a ``/`` inside
    a token, e.g. ``MELOXICAM/SM``, is preserved so the prefix still matches the
    catalog's ``name_gr``, which keeps the slash)."""
    out: list[str] = []
    for tok in re.split(r"\s+", name.strip()):
        if not tok or _FORM_OR_STRENGTH.match(tok):
            break
        out.append(tok)
    return " ".join(out).upper() or name.strip().upper()


# Per-process memo: normalised brand key → resolved record (or None for a known
# miss, so repeat misses don't re-query). Bounded; resets on restart (the
# pharmapi_session pattern). Different strengths of one brand share a key → 1 hit.
_BRAND_MEMO: dict[str, _Rec | None] = {}
_BRAND_MEMO_CAP = 4096


async def _by_substance_code(session: AsyncSession, codes: set[str]) -> dict[str, _Rec]:
    rows = await session.execute(
        select(DrugCatalog.substance_code, DrugCatalog.atc_code, DrugCatalog.name_en).where(
            DrugCatalog.substance_code.in_(codes)
        )
    )
    return _pick_unambiguous([(c, a, c, n) for c, a, n in rows if c])


async def _by_inn_name(session: AsyncSession, names_lower: set[str]) -> dict[str, _Rec]:
    rows = await session.execute(
        select(
            func.lower(DrugCatalog.name_en),
            DrugCatalog.atc_code,
            DrugCatalog.substance_code,
            DrugCatalog.name_en,
        ).where(func.lower(DrugCatalog.name_en).in_(names_lower))
    )
    return _pick_unambiguous([(low, a, s, n) for low, a, s, n in rows if low])


async def _by_commercial_name(session: AsyncSession, brands: set[str]) -> dict[str, _Rec]:
    """Prefix match on the normalised brand key against ``name_gr`` ("brand
    strength"), one query per distinct brand key — counts per patient are tiny,
    results memoised, LIKE wildcards escaped. Unambiguous-only."""
    out: dict[str, _Rec] = {}
    for brand in brands:
        key = _brand_key(brand)
        if len(key) < 3:
            continue
        if key in _BRAND_MEMO:
            rec = _BRAND_MEMO[key]
        else:
            safe = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = list(
                await session.execute(
                    select(
                        DrugCatalog.atc_code, DrugCatalog.substance_code, DrugCatalog.name_en
                    ).where(
                        func.upper(DrugCatalog.name_gr).like(f"{safe}%", escape="\\"),
                        DrugCatalog.atc_code != "",
                    )
                )
            )
            atcs = {r[0] for r in rows if r[0]}
            rec = (rows[0][0], rows[0][1], rows[0][2]) if len(atcs) == 1 else None
            if len(_BRAND_MEMO) < _BRAND_MEMO_CAP:
                _BRAND_MEMO[key] = rec
        if rec:
            out[brand] = rec
    return out


async def resolve_atcs(session: AsyncSession, hints: list[DrugHint]) -> list[ResolvedAtc | None]:
    """Resolve each hint to an ATC, aligned to the input order (``None`` = unresolved).

    Deterministic, catalog-backed. Order of the input is preserved so callers can
    zip results back onto their source rows (intolerances keep their severity/name;
    history items keep their identity)."""
    results: list[ResolvedAtc | None] = [None] * len(hints)
    if not hints:
        return results

    # Pass 1 — substance_code (exact, high).
    codes = {h.substance_code for h in hints if h.substance_code}
    code_map = await _by_substance_code(session, codes) if codes else {}
    for i, h in enumerate(hints):
        if h.substance_code and (rec := code_map.get(h.substance_code)):
            results[i] = ResolvedAtc(rec[0], "substance_code", "high", rec[1], rec[2])

    # Pass 2 — INN name (case-insensitive exact, high).
    names = {
        h.substance_name.strip().lower()
        for i, h in enumerate(hints)
        if results[i] is None and h.substance_name and h.substance_name.strip()
    }
    name_map = await _by_inn_name(session, names) if names else {}
    for i, h in enumerate(hints):
        if (
            results[i] is None
            and h.substance_name
            and (rec := name_map.get(h.substance_name.strip().lower()))
        ):
            results[i] = ResolvedAtc(rec[0], "inn_name", "high", rec[1], rec[2])

    # Pass 3 — brand name (normalised prefix, unambiguous only, low).
    brands = {
        h.commercial_name.strip()
        for i, h in enumerate(hints)
        if results[i] is None and h.commercial_name and h.commercial_name.strip()
    }
    brand_map = await _by_commercial_name(session, brands) if brands else {}
    for i, h in enumerate(hints):
        if (
            results[i] is None
            and h.commercial_name
            and (rec := brand_map.get(h.commercial_name.strip()))
        ):
            results[i] = ResolvedAtc(rec[0], "commercial_name", "low", rec[1], rec[2])

    return results
