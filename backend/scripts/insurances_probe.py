"""FT-2 (D-9) live probe — raw key-sets of the Tier-1 READ surfaces.

Answers ONE question against testeps: does any integrated read endpoint carry a
patient-level co-pay / participation field that our schemas silently drop?
(`PatientInsurancePayload` filters unknown keys, so the schema is not evidence
of absence — same reasoning as the BC-13a masterdata probe.)

Probes three read-only endpoints with the env credentials:

  1. GET /api/v1/prescriptions/search            (raw item key-set)
  2. GET /api/v1/common/getpatient               (raw payload key-set)
  3. GET /api/v1/common/getpatient/insurances    (raw entry key-set — the D-9 target)

PHI guard — this script NEVER prints AMKA, names, or field VALUES. Patient
keys are taken in memory from the pharmacy's own test queue and never shown.
Output is key paths + value type names + null/non-null only; that is what the
D-9 decision needs (field *presence*, not values — values are placeholder data
on testeps anyway).

Run (read-only; PHARMAPI_MOCK override per the established probe convention):

    docker compose exec -e PHARMAPI_MOCK=false backend \\
        python -m scripts.insurances_probe [--amka <AMKA>] [--max-patients 3]

Output feeds docs/b2b-core/insurances-probe.md. Throwaway after D-9 settles.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings  # noqa: E402
from app.services import pharmapi  # noqa: E402

# Substrings that would mark a key as the D-9 answer if present.
_COPAY_HINTS = ("particip", "percent", "copay", "co_pay", "contribution", "symmetox")


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    return type(value).__name__


def _walk(prefix: str, obj: object, out: dict[str, set[str]]) -> None:
    """Collect {key_path: {type names seen}} — keys and types only, never values."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            out.setdefault(path, set()).add(_type_name(v))
            _walk(path, v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk(f"{prefix}[]", item, out)


def _report(label: str, union: dict[str, set[str]]) -> None:
    print(f"\n[probe] === {label}: {len(union)} distinct key path(s) ===")
    for path in sorted(union):
        types = "/".join(sorted(union[path]))
        flag = " ← CO-PAY CANDIDATE" if any(h in path.lower() for h in _COPAY_HINTS) else ""
        print(f"[probe]   {path}: {types}{flag}")
    hits = [p for p in union if any(h in p.lower() for h in _COPAY_HINTS)]
    print(f"[probe] co-pay-shaped keys in {label}: {hits or 'NONE'}")


async def _run(amka_arg: str | None, max_patients: int) -> int:
    settings = get_settings()
    print(f"[probe] base = {settings.pharmapi_base}")
    try:
        me = await pharmapi.verify_pharmapi_credentials(
            settings.pharmapi_username, settings.pharmapi_password
        )
    except Exception as exc:
        print(f"[probe] AUTH FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    pharmapi._start_pharmapi_session(me)
    print("[probe] AUTH OK")

    # ── 1. raw /prescriptions/search — and harvest patient keys in memory ────
    # Wide explicit date range — ΗΔΥΚΑ search defaults to a narrow window, and an
    # empty result here would starve endpoints 2+3 of a patient key.
    window = {"from": "2025-01-01", "to": "2026-12-31"}
    raw_search = await pharmapi.pharmapi_get(
        "/api/v1/prescriptions/search",
        params={"page": 0, "size": 50, "prescribed": "false", **window},
    )
    search_union: dict[str, set[str]] = {}
    items = raw_search.get("contents", []) if isinstance(raw_search, dict) else []
    if not items:
        # Empty pending queue — fall back to an unfiltered search (same endpoint,
        # same item shape) so historical test prescriptions can supply patients.
        raw_search = await pharmapi.pharmapi_get(
            "/api/v1/prescriptions/search", params={"page": 0, "size": 50, **window}
        )
        items = raw_search.get("contents", []) if isinstance(raw_search, dict) else []
        print("[probe] pending queue empty — using unfiltered search")
    for item in items:
        _walk("item", item, search_union)
    print(f"[probe] search returned {len(items)} item(s)")
    _report("prescriptions/search items", search_union)

    amkas: list[str] = []
    if amka_arg:
        amkas = [amka_arg]
    else:
        for item in items:
            a = item.get("amka")
            if a and a not in amkas:
                amkas.append(a)
        amkas = amkas[:max_patients]
    if not amkas:
        print(
            "[probe] no patient key available (empty queue and no --amka) — endpoints 2+3 skipped",
            file=sys.stderr,
        )
        return 1
    print(f"\n[probe] probing {len(amkas)} patient(s) from the test queue (identifiers withheld)")

    # ── 2 + 3. raw getpatient + insurances per patient ───────────────────────
    patient_union: dict[str, set[str]] = {}
    insurance_union: dict[str, set[str]] = {}
    total_entries = 0
    for i, amka in enumerate(amkas, 1):
        raw_patient = await pharmapi.pharmapi_get(
            "/api/v1/common/getpatient", params={"patientamka": amka}
        )
        _walk("", raw_patient, patient_union)

        raw_ins = await pharmapi.pharmapi_get(
            "/api/v1/common/getpatient/insurances", params={"patientamka": amka}
        )
        # Walk the WHOLE response (envelope included) — a co-pay field could
        # sit beside `contents`, not inside the entries.
        _walk("", raw_ins, insurance_union)
        entries = raw_ins.get("contents", raw_ins) if isinstance(raw_ins, dict) else raw_ins
        n = len(entries) if isinstance(entries, list) else 1
        total_entries += n
        print(f"[probe] patient #{i}: insurances entries = {n}")

    _report("common/getpatient payload", patient_union)
    _report("getpatient/insurances response", insurance_union)
    print(
        f"\n[probe] DONE — patients probed: {len(amkas)}, insurance entries seen: {total_entries}"
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="FT-2/D-9 raw key-set probe (read-only)")
    p.add_argument("--amka", default=None, help="probe one specific patient (else: from queue)")
    p.add_argument("--max-patients", type=int, default=3)
    args = p.parse_args()
    return asyncio.run(_run(args.amka, args.max_patients))


if __name__ == "__main__":
    raise SystemExit(main())
