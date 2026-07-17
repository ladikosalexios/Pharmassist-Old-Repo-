"""Rule-based safety evaluation engine.

Evaluates a prescription against three data sources and returns a sorted list
of safety alerts. Replaces per-prescription MOCK_SAFETY_CHECKS for any rx_id
not already covered by that mock.
"""

import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import AdrSeverity, AlertStatus, CheckType
from ..db.models.safety_rule import SafetyRule
from ..schemas.safety import STATUS_ORDER, SafetyAlertPayload, SafetyChecksPayload
from ..utils.environment import is_mock_pharmapi
from .drug_catalog import names_for_atcs
from .patients import conditions, patient_intolerances, rx_history
from .prescriptions import MOCK_PRESCRIPTIONS
from .safety_checks import MOCK_SAFETY_CHECKS
from .spc import resolve_spc
from .substance_resolver import DrugHint, resolve_atcs

# Intolerances fixture for MOCK mode only. In live mode intolerances are fetched
# from Pharmapi (patients.patient_intolerances) and their activeSubstance is
# mapped to an ATC via services/substance_resolver — see _load_intolerances.
MOCK_INTOLERANCES: dict = {
    # P001 Maria Stavrou — "Penicillin (anaphylaxis)" allergy maps to J01CA (penicillins)
    "15031962456": [
        {"atcCode": "J01CA04", "name": "Amoxicillin", "severity": "SEVERE"},
    ],
}


_SEVERITY_TO_STATUS = {
    AdrSeverity.SEVERE: AlertStatus.BLOCK,
    AdrSeverity.MODERATE: AlertStatus.REVIEW,
    AdrSeverity.MILD: AlertStatus.REVIEW,
}

_CHECK_TYPE_NAME = {
    CheckType.INTERACTIONS: "Drug-Drug Interactions",
    CheckType.DUPLICATE_THERAPY: "Duplicate Therapy Check",
    CheckType.CONTRAINDICATIONS: "Contraindications",
    CheckType.DOSE_VALIDATION: "Dose Validation",
    CheckType.PREGNANCY: "Pregnancy",
    CheckType.G6PD: "G6PD Deficiency",
}


def _fold(s: str) -> str:
    """Lowercase + strip diacritics (Greek τόνοι, Latin accents) for loose matching."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _text_mentions(haystack: str, needle: str) -> bool:
    """True when ``needle`` (accent-folded) appears in ``haystack``. Terms under
    3 chars are ignored — too short to match a substance name without noise."""
    n = _fold(needle).strip()
    if len(n) < 3:
        return False
    return n in _fold(haystack)


# Patient factors gate the SPC's §4.3/§4.4 lines: a factor "applies" when its
# accent-folded keyword appears in the line (e.g. an elderly patient + a line
# mentioning "elderly"/"ηλικιωμένους"). Keywords are stored accent-free so they
# match _fold()ed text. Allergy factors match by substance name (_text_mentions),
# not by this map.
_CONDITION_KEYWORDS: dict[str, list[str]] = {
    "PREGNANCY": ["pregnan", "εγκυ", "κυησ", "κυοφορ"],
    "RENAL_SEVERE": ["renal", "νεφρ", "kidney"],
    "HEPATIC": ["hepatic", "ηπατ", "liver"],
    "G6PD": ["g6pd", "g-6-pd", "glucose-6", "6-φωσφ"],
}
_ELDERLY_KEYWORDS = ["elderly", "ηλικιωμ", "ανω των 65", "γηριατ", "older patient", "≥ 65", "≥65"]
_PEDIATRIC_KEYWORDS = ["children", "παιδ", "pediatric", "παιδιατ", "εφηβ", "adolescen"]


def _build_factors(intolerances: list[dict], pt_conditions: list, age) -> list[dict]:
    """Patient factors for SPC line-gating: recorded allergies, recorded
    conditions (pregnancy/renal/hepatic/G6PD), and derived age brackets.

    Each factor is ``{kind, label, keywords, severity}``. ``kind`` is one of
    ``allergy|condition|age``; allergy factors carry no keywords (matched by
    substance name)."""
    factors: list[dict] = []
    for i in intolerances or []:
        factors.append(
            {"kind": "allergy", "label": i["name"], "keywords": [], "severity": i.get("severity")}
        )
    for c in pt_conditions or []:
        kws = _CONDITION_KEYWORDS.get(c.condition_code)
        factors.append(
            {
                "kind": "condition",
                "label": c.name,
                "keywords": kws or [c.name],
                "severity": getattr(c, "severity", None),
            }
        )
    if isinstance(age, int):
        if age >= 65:
            factors.append(
                {"kind": "age", "label": "Ηλικιωμένος ασθενής (≥65)", "keywords": _ELDERLY_KEYWORDS}
            )
        elif age < 18:
            factors.append(
                {
                    "kind": "age",
                    "label": "Παιδιατρικός ασθενής (<18)",
                    "keywords": _PEDIATRIC_KEYWORDS,
                }
            )
    return factors


def _first_matching_factor(factors: list[dict], line: str) -> dict | None:
    """First factor whose allergy substance name / keyword appears in ``line``."""
    folded = _fold(line)
    for f in factors:
        if f["kind"] == "allergy":
            if _text_mentions(line, f["label"]):
                return f
        elif any(kw in folded for kw in f["keywords"]):
            return f
    return None


def _rule_to_alert(rule: SafetyRule, rx_id: str) -> SafetyAlertPayload:
    return SafetyAlertPayload(
        id=f"{rx_id}_{rule.rule_code}",
        name=_CHECK_TYPE_NAME.get(rule.check_type, rule.check_type),
        check_type=rule.check_type,
        status=_SEVERITY_TO_STATUS.get(rule.severity, AlertStatus.REVIEW),
        severity=rule.severity,
        message=rule.message_en,
        details=rule.details_en,
        recommended_action=rule.recommended_action_en,
        rx_id=rx_id,
        created_at=datetime.now(UTC),
    )


def live_rx_to_engine_shape(rx: dict, atc: str | None) -> dict:
    """Reshape a Pharmapi v2 search item into the dict shape evaluate_safety expects.

    `patientAmka` drives both `patient.id` and `patient.amka` — both are required
    by the engine for intolerance and condition lookups. If AMKA is absent from
    the Pharmapi response, all ATC-keyed patient checks will silently skip.
    The v2 search schema includes `amka` on every result, but callers should be
    aware of this dependency when handling edge cases.
    """
    amka = rx.get("patientAmka")
    return {
        "rxId": rx.get("rxId"),
        "patient": {"id": amka, "amka": amka},
        "medication": {"atcCode": atc, "nhrn": rx.get("medicineBarcode")},
    }


def _intolerance_hint(item: dict) -> DrugHint:
    """Build a resolver hint from a raw ΗΔΥΚΑ intolerance item. ``activeSubstance``
    is either an INN string or a ``{code, description}`` object."""
    sub = item.get("activeSubstance")
    if isinstance(sub, dict):
        code = sub.get("code")
        return DrugHint(
            substance_code=str(code) if code is not None else None,
            substance_name=sub.get("description"),
            raw=str(sub),
        )
    name = sub if isinstance(sub, str) else None
    return DrugHint(substance_name=name, raw=name)


def _intolerance_name(item: dict) -> str:
    sub = item.get("activeSubstance")
    if isinstance(sub, dict):
        return sub.get("description") or "Recorded intolerance"
    return sub if isinstance(sub, str) and sub else "Recorded intolerance"


async def _load_intolerances(session: AsyncSession, amka: str) -> list[dict]:
    """Normalised intolerance list (``{atcCode, name, severity}``) for §2.

    Mock mode → the ``MOCK_INTOLERANCES`` fixture (carries curated severity). Live
    mode → fetch from Pharmapi and resolve each ``activeSubstance`` to an ATC via
    the substance resolver; rows that don't resolve to a catalog ATC are dropped
    (they can't be matched safely). Live severity is unknown from ΗΔΥΚΑ, so a
    recorded intolerance defaults to SEVERE → BLOCK — matching the curated mock's
    posture for the same case (a documented allergy to the dispensed drug's class
    is a stop-and-confirm, not a soft note; BLOCK is advisory/overridable here, so
    conservative is correct and going live is never weaker than the demo). Parsing
    the intolerance TYPE into a graded severity is a follow-up."""
    if is_mock_pharmapi():
        return MOCK_INTOLERANCES.get(amka, [])
    raw = await patient_intolerances(amka)
    if not raw:
        return []
    resolved = await resolve_atcs(session, [_intolerance_hint(i) for i in raw])
    out: list[dict] = []
    for item, res in zip(raw, resolved, strict=True):
        if res is None:
            continue
        out.append(
            {
                "atcCode": res.atc_code,
                "name": _intolerance_name(item),
                "severity": AdrSeverity.SEVERE,
            }
        )
    return out


async def load_active_safety_rules(session: AsyncSession) -> list[SafetyRule]:
    """One-shot load of every active safety rule.

    Intended for callers that batch many evaluate_safety calls per request
    (e.g. the /v1 safety endpoint) so the per-rx WHERE-filtering moves to
    Python and the DB sees a single query instead of N.
    """
    result = await session.scalars(select(SafetyRule).where(SafetyRule.active == true()))
    return list(result.all())


async def checks_for_prescription(
    session: AsyncSession,
    rx_id: str,
    rx: dict | None,
    pharmacy_id: UUID,
    rules: list[SafetyRule] | None = None,
    intolerances: list[dict] | None = None,
    verbose_spc: bool = False,
) -> SafetyChecksPayload:
    """Single source of truth for a prescription's safety checks.

    Demo prescriptions (rx_id in MOCK_SAFETY_CHECKS) are served from their
    curated, clinically-authored checklist; everything else is evaluated by
    the rule engine. BOTH the prescription detail view and the per-rx
    verification view (/safety-checks/{rx}) call this, so the two views can
    never disagree about a prescription — a block on one is a block on the
    other by construction.

    ``intolerances`` is forwarded to ``evaluate_safety``: the live dashboard
    passes ``[]`` so a per-rx loop does NOT fire one ΗΔΥΚΑ intolerance call per
    prescription; the single-rx verification view leaves it ``None`` so allergy
    screening runs where a specific prescription is scrutinised.
    """
    mock_checks = MOCK_SAFETY_CHECKS.get(rx_id)
    if mock_checks is not None:
        checks = []
        for c in mock_checks:
            payload = SafetyAlertPayload.model_validate(c)
            # The curated dicts don't carry rx_id, and their `id` is generic
            # ("interactions", …). Stamp both so dashboard cards link back to
            # the right prescription and React keys stay unique across the
            # queue — matching what the engine path emits.
            payload.rx_id = rx_id
            payload.id = f"{rx_id}_{c['id']}"
            checks.append(payload)
        return SafetyChecksPayload(rx_id=rx_id, checks=checks, source="mock")
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return await evaluate_safety(
        session, rx, pharmacy_id, rules=rules, intolerances=intolerances, verbose_spc=verbose_spc
    )


async def evaluate_safety(
    session: AsyncSession,
    rx: dict,
    pharmacy_id: UUID,
    rules: list[SafetyRule] | None = None,
    history_atcs: set[str] | None = None,
    patient_conditions: list | None = None,
    intolerances: list[dict] | None = None,
    verbose_spc: bool = False,
) -> SafetyChecksPayload:
    """Evaluate a single prescription against the safety-rule catalogue.

    Pass `rules` from a prior `load_active_safety_rules(session)` to skip
    the per-call DB round-trip. When `rx["medication"]["atcCode"]` is
    missing (e.g. live Pharmapi search hasn't been enriched yet), all
    ATC-keyed checks are skipped — DB-condition checks that don't need
    ATC still run when relevant rule shape supports it.

    The two seams for the B2B /v1 path (additive — B2C behaviour is
    unchanged when they are omitted):

    * `history_atcs` — explicit co-medication ATC set. When provided, the
      interaction/duplicate checks match against it directly instead of
      deriving history from the (mock-only) prescription store. This is what
      makes drug-drug checks work in live mode for callers that supply the
      patient's other drugs.
    * `patient_conditions` — pre-loaded condition rows (each carrying a
      `.condition_code`). When provided, the per-pharmacy DB read is skipped;
      /v1 loads them from b2b_patient_conditions scoped to its location.
    * `intolerances` — pre-loaded intolerance dicts (`{atcCode, name, severity}`).
      When provided, the internal load is skipped. `None` triggers the B2C load
      (`_load_intolerances`: MOCK fixture in mock mode, live Pharmapi fetch +
      substance→ATC resolution in live mode). The /v1 path passes an explicit
      list (empty until it opts into consented allergy screening) so the engine
      never makes a legacy-credential intolerance call under a B2B context.

    ``verbose_spc`` (single-rx review path only) enriches the result from the
    drug's own SPC (``resolve_spc``): patient-specific contraindication matches,
    an advisory precautions/interactions pointer, and — for every screening path
    that ran clean — a green positive-confirmation row, so the review card is
    always populated rather than blank. It is OFF by default: the dashboard batch
    and the /v1 B2B path keep the lean, alerts-only output (and their tests stay
    byte-identical). It requires a real ``session`` (SPC + condition lookups).
    """
    if rules is None:
        rules = await load_active_safety_rules(session)

    # Multi-med prescriptions (ΗΔΥΚΑ therapy lines) carry a `medications` list;
    # single-med prescriptions keep the legacy `medication` dict. Every line is
    # evaluated, and each line's SIBLING lines join the co-medication set so
    # line-vs-line interactions fire (e.g. a statin and a macrolide prescribed
    # together on one prescription). `seen` is shared across lines, so a rule
    # never produces duplicate alerts however many lines match it.
    medication = rx.get("medication") or {}
    meds = rx.get("medications")
    if not (isinstance(meds, list) and meds):
        meds = [medication] if isinstance(medication, dict) else [{}]
    med_atcs = {m.get("atcCode") for m in meds if isinstance(m, dict) and m.get("atcCode")}

    patient = rx.get("patient") or {}
    patient_id = patient.get("id")
    amka = patient.get("amka")
    age = patient.get("age")

    # Co-medication display names (brand) for the §4.5 cross-ref + the screened
    # confirmation: sibling therapy lines now, patient history added below.
    co_med_names: set[str] = {
        m["drugName"] for m in meds if isinstance(m, dict) and m.get("drugName")
    }

    checks: list[SafetyAlertPayload] = []
    seen: set[str] = set()
    # Track which screening paths raised an alert, so the verbose_spc positive
    # confirmations below only fire for a path that ran clean (never a false
    # "all clear"). An allergy match (§2 or an SPC contraindication that matched
    # an intolerance) flips intolerance_fired independently of a condition match.
    interaction_fired = False
    intolerance_fired = False
    interaction_screened = False

    # --- 1. Drug-drug interactions & duplicate therapy (co-medication set) ---
    # Pre-filter rules so we don't make the rx_history call (Pharmapi round-trip
    # in live mode) when no interaction/duplicate rules can possibly match.
    # Live mode: Pharmapi history returns commercialName + no barcode, so
    # co-medication ATCs are resolved from the brand name via the substance
    # resolver (drug_catalog brand→ATC); mock history resolves via MOCK_PRESCRIPTIONS.
    # Derived ONCE for the prescription; per-line siblings are added in the loop.
    interaction_rules = [
        r for r in rules if r.check_type in (CheckType.INTERACTIONS, CheckType.DUPLICATE_THERAPY)
    ]
    if med_atcs and interaction_rules and history_atcs is None and patient_id:
        history = await rx_history(patient_id)
        history_atcs = set()
        brand_hints: list[DrugHint] = []
        for entry in history:
            if entry["rxId"] == rx["rxId"]:
                continue
            if entry.get("drugName"):
                co_med_names.add(entry["drugName"])
            hist_rx = MOCK_PRESCRIPTIONS.get(entry["rxId"])
            if hist_rx:
                history_atcs.add(hist_rx["medication"]["atcCode"])
            elif entry.get("drugName"):
                brand_hints.append(
                    DrugHint(commercial_name=entry["drugName"], raw=entry["drugName"])
                )
        if brand_hints:
            history_atcs |= {r.atc_code for r in await resolve_atcs(session, brand_hints) if r}

    # Loaded once, shared by every line's intolerance / condition screening.
    if med_atcs and amka and intolerances is None:
        intolerances = await _load_intolerances(session, amka)
    pt_conditions = patient_conditions
    # The verbose review path cross-references conditions against the SPC's
    # contraindications text (not just the condition-rule table), so load them
    # up-front even when no rule references this ATC.
    if verbose_spc and amka and pt_conditions is None and session is not None:
        pt_conditions = await conditions(session, amka, pharmacy_id)

    # Verbose review path: patient factors (allergies + conditions + age brackets)
    # gate the SPC §4.3/§4.4 lines, and co-medication ATCs resolve to INN names so
    # they can be matched against the SPC §4.5 interactions text.
    factors: list[dict] = []
    inn_names: dict[str, str] = {}
    if verbose_spc:
        factors = _build_factors(intolerances or [], pt_conditions or [], age)
        all_co_atcs = (history_atcs or set()) | med_atcs
        if all_co_atcs and session is not None:
            inn_names = await names_for_atcs(session, all_co_atcs)

    for med in meds:
        rx_atc = med.get("atcCode") if isinstance(med, dict) else None
        if not rx_atc:
            continue

        co_atcs = set(history_atcs or set()) | (med_atcs - {rx_atc})
        if interaction_rules and co_atcs:
            interaction_screened = True
            # Bidirectional ATC match: WARFARIN_ASPIRIN_BLEED fires whether
            # warfarin is the new or the historical/sibling drug.
            for rule in interaction_rules:
                matches = (rule.trigger_atc == rx_atc and rule.conflicting_atc in co_atcs) or (
                    rule.conflicting_atc == rx_atc and rule.trigger_atc in co_atcs
                )
                if matches and rule.rule_code not in seen:
                    seen.add(rule.rule_code)
                    interaction_fired = True
                    checks.append(_rule_to_alert(rule, rx["rxId"]))

        # --- 2. Intolerances / contraindications (Pharmapi) ---
        # Match on the first four characters of the ATC code (level-3 class) so
        # that a penicillin intolerance catches all J01CA-* drugs, not just the
        # exact molecule recorded.
        if amka:
            for intol in intolerances or []:
                if rx_atc[:4] == intol["atcCode"][:4]:
                    key = f"INTOLERANCE_{intol['atcCode'][:4]}"
                    if key not in seen:
                        seen.add(key)
                        intolerance_fired = True
                        checks.append(
                            SafetyAlertPayload(
                                id=f"{rx['rxId']}_INTOLERANCE_{intol['atcCode'][:4]}",
                                name=_CHECK_TYPE_NAME[CheckType.CONTRAINDICATIONS],
                                check_type=CheckType.CONTRAINDICATIONS,
                                status=_SEVERITY_TO_STATUS.get(
                                    intol["severity"], AlertStatus.REVIEW
                                ),
                                severity=intol["severity"],
                                message=intol["name"],
                                rx_id=rx["rxId"],
                                created_at=datetime.now(UTC),
                            )
                        )

        # --- 3. Patient-specific conditions (DB) ---
        # Skip the DB call entirely when no rule could possibly match this
        # line's ATC — saves a query per evaluated prescription.
        condition_rule_candidates = [
            r for r in rules if r.trigger_atc == rx_atc and r.trigger_condition_code is not None
        ]
        if amka and condition_rule_candidates:
            if pt_conditions is None:
                pt_conditions = await conditions(session, amka, pharmacy_id)
            condition_codes = {c.condition_code for c in pt_conditions}

            if condition_codes:
                for rule in condition_rule_candidates:
                    if rule.rule_code in seen:
                        continue
                    if rule.trigger_condition_code in condition_codes:
                        seen.add(rule.rule_code)
                        checks.append(_rule_to_alert(rule, rx["rxId"]))

        # --- 4. SPC-driven checks (verbose single-rx review path only) ---
        # The drug's OWN SPC gives coverage beyond the ~7 seeded rule classes.
        # resolve_spc walks barcode → ATC → MOCK_SPC; None means no document.
        if verbose_spc:
            spc = await resolve_spc(
                session, rx_atc, med.get("nhrn") if isinstance(med, dict) else None
            )
            if spc:
                # 4a. Factor-gated §4.3 contraindications → patient-specific.
                # Only lines matching a recorded allergy / condition / age bracket
                # surface here (the full SPC lists live on the medication card); a
                # match is a real, this-patient alert.
                for line in spc.get("contraindications") or []:
                    f = _first_matching_factor(factors, line)
                    if f is None:
                        continue
                    key = f"SPC_CONTRA_{rx_atc[:4]}_{_fold(f['label'])}"
                    if key in seen:
                        continue
                    seen.add(key)
                    if f["kind"] == "allergy":
                        intolerance_fired = True
                    block = f["kind"] == "condition" or (
                        f["kind"] == "allergy" and f.get("severity") == AdrSeverity.SEVERE
                    )
                    checks.append(
                        SafetyAlertPayload(
                            id=f"{rx['rxId']}_{key}",
                            name="Αντένδειξη — αφορά τον ασθενή",
                            check_type=CheckType.CONTRAINDICATIONS,
                            status=AlertStatus.BLOCK if block else AlertStatus.REVIEW,
                            severity=f.get("severity"),
                            message=line,
                            details=f"Σχετίζεται με: {f['label']}",
                            recommended_action="Επιβεβαιώστε με τον συνταγογράφο πριν τη χορήγηση.",
                            rx_id=rx["rxId"],
                            created_at=datetime.now(UTC),
                        )
                    )
                # 4b. §4.4 precautions. Factor-matched lines are ELEVATED to a
                # this-patient REVIEW; the rest go in ONE generic pointer so the
                # card shows precautions once, not repeated per line.
                precs = spc.get("precautions") or []
                remaining: list[str] = []
                for line in precs:
                    f = _first_matching_factor(factors, line)
                    if f is None:
                        remaining.append(line)
                        continue
                    key = f"SPC_PREC_{rx_atc[:4]}_{_fold(line)[:40]}"
                    if key in seen:
                        continue
                    seen.add(key)
                    checks.append(
                        SafetyAlertPayload(
                            id=f"{rx['rxId']}_{key}",
                            name="Προφύλαξη — αφορά τον ασθενή",
                            check_type=CheckType.SPC_ALIGNMENT,
                            status=AlertStatus.REVIEW,
                            message=line,
                            details=f"Σχετίζεται με: {f['label']}",
                            recommended_action="Ελέγξτε την προφύλαξη πριν την παράδοση.",
                            rx_id=rx["rxId"],
                            created_at=datetime.now(UTC),
                        )
                    )
                pkey = f"SPC_PRECAUTIONS_{rx_atc}"
                if remaining and pkey not in seen:
                    seen.add(pkey)
                    checks.append(
                        SafetyAlertPayload(
                            id=f"{rx['rxId']}_{pkey}",
                            name="Προφυλάξεις (ΠΧΠ)",
                            check_type=CheckType.SPC_ALIGNMENT,
                            status=AlertStatus.REVIEW,
                            message=f"{len(remaining)} σημεία προσοχής — δείτε λεπτομέρειες.",
                            details=" • ".join(remaining),
                            recommended_action="Ελέγξτε τις προφυλάξεις της ΠΧΠ πριν την παράδοση.",
                            rx_id=rx["rxId"],
                            created_at=datetime.now(UTC),
                        )
                    )
                # 4c. §4.5 co-medication cross-ref. Each co-med (sibling line or
                # history), by INN and brand, is matched against the SPC's §4.5
                # interactions text (or MOCK structured pairs) — catching pairs the
                # 18 seeded rules don't cover.
                inter_text = spc.get("interactionsText") or ""
                struct_inter = spc.get("majorInteractions") or []
                own_name = med.get("drugName") if isinstance(med, dict) else None
                line_co_atcs = (history_atcs or set()) | (med_atcs - {rx_atc})
                terms = {inn_names[a] for a in line_co_atcs if a in inn_names}
                terms |= {nm for nm in co_med_names if nm and nm != own_name}
                if terms and (inter_text or struct_inter):
                    interaction_screened = True
                    for display in terms:
                        hit = _text_mentions(inter_text, display) or any(
                            _text_mentions(str(p.get("drug", "")), display) for p in struct_inter
                        )
                        if not hit:
                            continue
                        ikey = f"SPC_INTERACTION_{rx_atc[:4]}_{_fold(display)[:40]}"
                        if ikey in seen:
                            continue
                        seen.add(ikey)
                        interaction_fired = True
                        checks.append(
                            SafetyAlertPayload(
                                id=f"{rx['rxId']}_{ikey}",
                                name="Πιθανή αλληλεπίδραση (ΠΧΠ §4.5)",
                                check_type=CheckType.INTERACTIONS,
                                status=AlertStatus.REVIEW,
                                message=f"Πιθανή αλληλεπίδραση με {display}.",
                                details="Αναφέρεται στις αλληλεπιδράσεις της ΠΧΠ (§4.5).",
                                recommended_action="Επιβεβαιώστε πριν τη χορήγηση.",
                                rx_id=rx["rxId"],
                                created_at=datetime.now(UTC),
                            )
                        )

    # --- Positive confirmations (verbose review path) ---
    # For each screening path that RAN WITH DATA and stayed clean, add a green
    # row so the card reads as verified, not blank. Only paths that actually ran
    # get a confirmation — never a false "all clear" for data we couldn't fetch.
    if verbose_spc:
        allergy_screened = amka is not None and intolerances is not None
        if allergy_screened and not intolerance_fired:
            checks.append(
                SafetyAlertPayload(
                    id=f"{rx['rxId']}_OK_ALLERGY",
                    name="Δεν εντοπίστηκε καταγεγραμμένη αλλεργία που να αφορά το φάρμακο.",
                    check_type=CheckType.CONTRAINDICATIONS,
                    status=AlertStatus.OK,
                    message="",
                    rx_id=rx["rxId"],
                    created_at=datetime.now(UTC),
                )
            )
        if interaction_screened and not interaction_fired:
            # Name the co-meds that were screened when we have them; else fall
            # back to a count of co-medication ATCs.
            names = sorted(set(co_med_names) | set(inn_names.values()))
            if names:
                shown = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
                label = f"Ελέγχθηκαν {len(names)} συγχορηγούμενα ({shown}) — καμία γνωστή αλληλεπίδραση."
            else:
                n = max(len((history_atcs or set()) | med_atcs) - 1, 0)
                label = f"Καμία γνωστή αλληλεπίδραση με {n} συγχορηγούμενο/-α φάρμακο/-α."
            checks.append(
                SafetyAlertPayload(
                    id=f"{rx['rxId']}_OK_INTERACTION",
                    name=label,
                    check_type=CheckType.INTERACTIONS,
                    status=AlertStatus.OK,
                    message="",
                    rx_id=rx["rxId"],
                    created_at=datetime.now(UTC),
                )
            )

    checks.sort(key=lambda a: STATUS_ORDER.get(a.status, 99))
    return SafetyChecksPayload(rx_id=rx["rxId"], checks=checks, source="engine")
