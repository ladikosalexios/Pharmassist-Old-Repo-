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


def _pick_unambiguous(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """Group (key, atc) pairs and keep a key only when its rows agree on ONE ATC.

    Two brands of the same substance share an ATC (kept); a key that maps to two
    distinct ATCs (e.g. an ambiguous brand substring) is dropped rather than
    guessed — a false interaction is worse than a missed one here."""
    groups: dict[str, set[str]] = {}
    for key, atc in pairs:
        if atc:
            groups.setdefault(key, set()).add(atc)
    return {k: next(iter(v)) for k, v in groups.items() if len(v) == 1}


async def _by_substance_code(session: AsyncSession, codes: set[str]) -> dict[str, str]:
    rows = await session.execute(
        select(DrugCatalog.substance_code, DrugCatalog.atc_code).where(
            DrugCatalog.substance_code.in_(codes)
        )
    )
    return _pick_unambiguous([(c, a) for c, a in rows if c])


async def _by_inn_name(session: AsyncSession, names_lower: set[str]) -> dict[str, str]:
    rows = await session.execute(
        select(func.lower(DrugCatalog.name_en), DrugCatalog.atc_code).where(
            func.lower(DrugCatalog.name_en).in_(names_lower)
        )
    )
    return _pick_unambiguous([(n, a) for n, a in rows if n])


async def _by_commercial_name(session: AsyncSession, brands: set[str]) -> dict[str, str]:
    """Substring match on ``name_gr`` (which is "brand strength"), one query per
    brand — brand counts per patient are tiny, and LIKE wildcards in the upstream
    value are escaped so a stray ``%`` can't broaden the match."""
    out: dict[str, str] = {}
    for brand in brands:
        safe = brand.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = await session.scalars(
            select(DrugCatalog.atc_code).where(
                DrugCatalog.name_gr.ilike(f"%{safe}%", escape="\\"),
                DrugCatalog.atc_code != "",
            )
        )
        atcs = {a for a in rows if a}
        if len(atcs) == 1:
            out[brand] = next(iter(atcs))
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
        if h.substance_code and (atc := code_map.get(h.substance_code)):
            results[i] = ResolvedAtc(atc, "substance_code", "high")

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
            and (atc := name_map.get(h.substance_name.strip().lower()))
        ):
            results[i] = ResolvedAtc(atc, "inn_name", "high")

    # Pass 3 — brand name (substring, unambiguous only, low).
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
            and (atc := brand_map.get(h.commercial_name.strip()))
        ):
            results[i] = ResolvedAtc(atc, "commercial_name", "low")

    return results
