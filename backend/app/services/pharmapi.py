"""Pharmapi (ΗΔΥΚΑ) HTTP client + 24h session tracker.

In production the session state would live in Redis or a real DB; here it's
just a per-process dict so a `uvicorn --reload` reset clears it.

Pharmapi credentials are sourced from the centralised settings.
"""

import logging
import os
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from app.schemas.patients import PatientPayload
from app.utils.dates import age_from_date

from ..config import get_settings
from ..constants import PrescriptionStatus

logger = logging.getLogger(__name__)

# Module-level constants kept for backward compat — anything that imports
# these by name keeps working. Sourced from settings at first import.
_settings = get_settings()
PHARMAPI_BASE = _settings.pharmapi_base
logger.info("Pharmapi base URL: %s", PHARMAPI_BASE)
PHARMAPI_USER = _settings.pharmapi_username
PHARMAPI_PASS = _settings.pharmapi_password
PHARMAPI_API_KEY = _settings.pharmapi_api_key
SESSION_WINDOW_SECONDS = _settings.pharmapi_session_window_seconds


# In-memory 24h session tracker. Mutated by the /pharmapi/connect handler.
pharmapi_session: dict = {
    "connected": False,
    "connected_at": None,  # ISO timestamp
    "connected_at_ts": 0.0,  # unix timestamp
    "user_data": None,  # response from /api/v1/user/me
    "pharmacy_id": None,  # units[0].id from /api/v1/user/me — required for patient history endpoints
}


def session_is_valid() -> bool:
    if not pharmapi_session["connected"]:
        return False
    elapsed = time.time() - pharmapi_session["connected_at_ts"]
    return elapsed < SESSION_WINDOW_SECONDS


def pharmapi_headers() -> dict:
    """Headers required on every Pharmapi call."""
    if not PHARMAPI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="PHARMAPI_API_KEY not set. Add it to your environment — it was in your ΗΔΥΚΑ registration email.",
        )
    return {
        "Accept": "application/json",
        "Api-Key": PHARMAPI_API_KEY,
    }


def _parse_pharmapi_error(r: httpx.Response) -> str:
    """Extract ΗΔΥΚΑ error code from response body."""
    try:
        data = r.json()
        return data.get("errorCode") or data.get("message") or r.text[:200]
    except Exception:
        return r.text[:200]


async def pharmapi_get(
    path: str,
    accept_xml: bool = False,
    params: dict | None = None,
) -> dict | list:
    """Authenticated GET to Pharmapi. Raises HTTPException on failure.

    `params` is passed through to httpx so query-string values are properly
    URL-encoded. Callers MUST NOT pre-build a query string in `path` from
    untrusted input — pass them via `params` instead.

    Return type is `dict | list` because `r.json()` mirrors whatever the
    upstream returns — most endpoints return a paginated object, but
    `/api/v1/version` returns a top-level array. Callers are expected to
    narrow.
    """
    url = f"{PHARMAPI_BASE}{path}"
    headers = pharmapi_headers()
    if accept_xml:
        headers["Accept"] = "application/xml"
    print(f"[Pharmapi] GET {url} params={params}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            url,
            auth=(PHARMAPI_USER, PHARMAPI_PASS),
            headers=headers,
            params=params,
        )
    print(f"[Pharmapi] {r.status_code} — {r.text[:500]}")

    if r.status_code == 200:
        # API returns XML for some endpoints, JSON for others
        content_type = r.headers.get("content-type", "")
        if "xml" in content_type:
            # Return raw XML as a dict with one key for now
            return {"raw_xml": r.text}
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}

    # Full raw error for debugging
    try:
        err_body = r.json()
        err = str(err_body)
    except Exception:
        err_body = {}
        err = r.text

    if "G12" in err:
        raise HTTPException(
            502, "Pharmapi: no active connection — call POST /pharmapi/connect first"
        )
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(
            502,
            "Pharmapi: 24h session expired — log into https://test.e-prescription.gr/epregen2/ first, then retry",
        )
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    if r.status_code == 401:
        raise HTTPException(502, f"Pharmapi: bad credentials — {err}")
    raise HTTPException(502, f"Pharmapi error {r.status_code}: {err}")


async def verify_pharmapi_credentials(username: str, password: str) -> dict:
    """Validate caller-supplied creds against Pharmapi GET /api/v1/user/me.

    Returns the parsed JSON pharmacist profile on 200. Raises:
      - 401 'Invalid Pharmapi credentials' if Pharmapi rejects the password
      - 500 (G15/G11) if Api-Key is missing or invalid
      - 502 (G14) if the 24h session window has expired
      - 502 for other upstream failures
    """
    url = f"{PHARMAPI_BASE}/api/v1/user/me"
    headers = pharmapi_headers()  # already defaults Accept: application/json
    print(f"[Pharmapi] AUTH {url} as {username}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, auth=(username, password), headers=headers)
    print(f"[Pharmapi] {r.status_code} — {r.text[:300]}")

    if r.status_code == 200:
        try:
            return r.json()
        except Exception as exc:
            raise HTTPException(502, "Pharmapi: /user/me did not return JSON") from exc

    err = _parse_pharmapi_error(r)
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(
            502,
            "Pharmapi: 24h session expired — log into https://test.e-prescription.gr/epregen2/ first, then retry",
        )
    if r.status_code == 401:
        raise HTTPException(401, "Invalid Pharmapi credentials")
    raise HTTPException(502, f"Pharmapi error {r.status_code}: {err}")


async def verify_pharmapi_credentials_with_decrypted(username: str, password: str) -> dict:
    """Login-flow wrapper around verify_pharmapi_credentials.

    Defaults to LIVE — production must never silently fall into mock mode
    because the env var was missing. Set PHARMAPI_MOCK=true explicitly to
    bypass the upstream call (local dev, CI, smoke tests); both compose.yaml
    and tests/test_auth_db.py already do this. `username` / `password` are
    still required — bcrypt over the local password_hash must have already
    passed, and we want the same call shape in mock and live mode.
    """
    if os.getenv("PHARMAPI_MOCK", "false").lower() not in ("false", "0", "no"):
        return {
            "email": f"{username}@pharmapi.local",
            "name": {"firstname": "Mock", "lastname": "Pharmacist"},
            "pharmacy": {"name": "Mock Pharmacy", "id": 0},
            "units": [{"id": 0, "name": "Mock Pharmacy"}],
        }
    return await verify_pharmapi_credentials(username, password)


def _start_pharmapi_session(user_data: dict) -> None:
    """Pin the 24h connection window — shared by /auth/login and /pharmapi/connect."""
    units = user_data.get("units", [])
    pharmapi_session["pharmacy_id"] = (
        units[0].get("id") if units else user_data.get("pharmacy", {}).get("id")
    )
    now = time.time()
    pharmapi_session.update(
        {
            "connected": True,
            "connected_at": datetime.now(UTC).isoformat(),
            "connected_at_ts": now,
            "user_data": user_data,
        }
    )


def get_pharmacy_id() -> int | str:
    """Return the active pharmacy unit id or raise if no valid session exists."""
    if not session_is_valid():
        raise HTTPException(
            status_code=403,
            detail="No active Pharmapi session — call POST /pharmapi/connect first",
        )
    pid = pharmapi_session.get("pharmacy_id")
    if pid is None:
        raise HTTPException(
            status_code=500,
            detail="Session active but pharmacy_id not set — this is a bug",
        )
    return pid


# ── Prescription search XML parser ──────────────────────────────────────────


def _el(parent: ET.Element, tag: str) -> str | None:
    """Safe text extraction from an XML element."""
    el = parent.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _date(raw: str | None) -> str | None:
    """Trim 'YYYY-MM-DD HH:MM:SS' → 'YYYY-MM-DD'."""
    if not raw:
        return None
    return raw.strip()[:10]


_PHARMAPI_STATUS_MAP = {
    "PENDING": PrescriptionStatus.PENDING,
    "ACTIVE": PrescriptionStatus.PENDING,  # assume active = awaiting dispense
    "COMPLETED": PrescriptionStatus.COMPLETED,
    "EXECUTED": PrescriptionStatus.COMPLETED,
    "CANCELLED": PrescriptionStatus.FLAGGED,
    "EXPIRED": PrescriptionStatus.FLAGGED,
    "PARTIAL": PrescriptionStatus.PENDING,  # partially dispensed — still actionable
}


def _map_pharmapi_status(pharmapi_status: str | None) -> str:
    """
    Map ΗΔΥΚΑ prescription status string to our internal status.

    Unknown / missing values fall back to "UNKNOWN" (NOT "PENDING") so a status
    string we haven't enumerated never makes a prescription dispensable in our
    UI. Unmapped values are logged so the gap is visible — extend the map when
    new real-world values are observed.
    """
    if not pharmapi_status:
        return PrescriptionStatus.UNKNOWN
    s = pharmapi_status.upper().strip()
    if s not in _PHARMAPI_STATUS_MAP:
        print(f"[Pharmapi] WARNING: unmapped status '{pharmapi_status}' — defaulting to UNKNOWN")
        return PrescriptionStatus.UNKNOWN
    return _PHARMAPI_STATUS_MAP[s]


# DEPRECATED — Pharmapi v2 returns JSON. Kept until confirmed safe to remove.
def parse_prescription_search_xml(xml_text: str) -> list[dict]:
    """
    Parse the XML response from GET /api/v1/prescriptions/search.

    Returns a list of normalised prescription queue items. Each item matches
    the shape expected by the /prescriptions dashboard (same as MOCK_QUEUE_BASE),
    with additional Pharmapi-specific fields preserved.

    Fields NOT available in the search response (populated as None):
      - medication / drugName  → requires a per-prescription detail call
      - physician              → requires a per-prescription detail call
    """
    if not xml_text:
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise HTTPException(502, f"Pharmapi: could not parse prescription XML — {exc}") from exc

    items = []
    for item in root.findall(".//contents/item"):
        patient = item.find("patientInfo")
        status_el = item.find("status")
        insurance_el = item.find("socialInsurance")

        amka = _el(patient, "amka") if patient is not None else None
        first_name = _el(patient, "firstName") if patient is not None else None
        last_name = _el(patient, "lastName") if patient is not None else None
        patient_name = " ".join(filter(None, [first_name, last_name])) or "Άγνωστος"

        pharmapi_status = _el(status_el, "status") if status_el is not None else None

        items.append(
            {
                # ── Core fields (same shape as MOCK_QUEUE_BASE) ─────────────────
                "rxId": _el(item, "barcode"),
                "patientName": patient_name,
                "medication": None,  # not in search — populated on detail fetch
                "physician": None,  # not in search — populated on detail fetch
                "date": _date(_el(item, "issueDate")),
                "status": _map_pharmapi_status(pharmapi_status),
                # ── Extra Pharmapi fields (useful for UI / filtering) ────────────
                "patientAmka": amka,
                "expiryDate": _date(_el(item, "expiryDate")),
                "executions": _el(item, "executions"),
                "medicineDrug": _el(item, "medicineDrug") == "true",
                "socialInsurance": (
                    _el(patient, "socialInsuranceShortName")
                    if patient is not None
                    else (_el(insurance_el, "shortName") if insurance_el is not None else None)
                ),
                "pharmApiStatus": pharmapi_status,  # raw value for debugging
            }
        )

    return items


async def pharmapi_check_version() -> None:
    """Call GET /api/v1/version and log the current API version at startup."""
    try:
        data = await pharmapi_get("/api/v1/version")
        versions = data if isinstance(data, list) else data.get("content", [])
        if versions:
            latest = versions[0]
            logger.info(
                "Pharmapi API version: %s (released %s)",
                latest.get("version"),
                latest.get("releaseDate"),
            )
            logger.info("Pharmapi changelog: %s", latest.get("changelog", "none"))
        else:
            logger.warning(
                "Pharmapi version endpoint returned empty or unexpected response: %r",
                data,
            )
    except Exception as exc:
        logger.warning("Pharmapi version check failed — %s", exc)


async def pharmapi_execute_prescription(
    barcode: str,
    eof_licence_no: str,
) -> dict:
    """Pretend-POST a dispense to ΗΔΥΚΑ. Mock-only for now.

    In mock mode (PHARMAPI_MOCK=true, default) returns a synthetic exec_ref
    immediately — no network. This is what the approve flow persists on
    documentation_logs.pharmapi_exec_ref so the row carries a plausible
    "we told ΗΔΥΚΑ this was dispensed" reference.

    In live mode this would POST to the ΗΔΥΚΑ dispense endpoint; that wiring
    isn't in place yet (live approve still 501s upstream of this call).
    """
    if os.getenv("PHARMAPI_MOCK", "true").lower() not in ("false", "0", "no"):
        return {
            "exec_ref": f"MOCK-EXEC-{uuid.uuid4().hex[:12].upper()}",
            "executed_at": datetime.now(UTC).isoformat(),
            "status": "EXECUTED",
            "barcode": barcode,
            "eof_licence_no": eof_licence_no,
        }
    raise HTTPException(501, "Live ΗΔΥΚΑ dispense POST not yet implemented")


def _parse_prescription_search_json(items: list) -> list[dict]:
    """Map Pharmapi v2 JSON search items to our internal queue shape."""
    out: list[dict] = []
    try:
        for item in items:
            medicines = item.get("medicines") or []
            social_insurance = item.get("socialInsurance") or {}
            pharmapi_status = item.get("status")
            out.append(
                {
                    "rxId": item.get("barcode"),
                    "patientName": item.get("patientName") or "Άγνωστος",
                    "patientAmka": item.get("amka"),
                    "medication": medicines[0]["name"] if medicines else None,
                    "physician": item.get("doctorName"),
                    "date": item.get("issueDate"),
                    "expiryDate": item.get("expiryDate"),
                    "status": _map_pharmapi_status(pharmapi_status),
                    "socialInsurance": social_insurance.get("name"),
                    "pharmApiStatus": pharmapi_status,
                    "repeatNo": item.get("repeatNo"),
                    "totalRepeats": item.get("totalRepeats"),
                    # medicineDrug hardcoded False per T1 spec — XML parser derived
                    # it from upstream; revisit if the v2 JSON exposes an equivalent.
                    "medicineDrug": False,
                    "executions": None,
                }
            )
    except (KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(502, f"Pharmapi: could not parse prescription JSON — {exc}") from exc
    return out


async def pharmapi_search_prescriptions(
    prescription_status: str | None = None,
    page: int = 0,
    size: int = 50,
    from_date: str | None = None,
    to_date: str | None = None,
    barcode: str | None = None,
    amka: str | None = None,
) -> list[dict]:
    """
    Fetch the prescription queue (or a specific prescription) from Pharmapi.

    prescription_status=<value> → filter by Pharmapi prescriptionStatus (e.g. "ACTIVE", "EXECUTED")
    barcode=<code>              → find one specific prescription by barcode

    Returns a list of normalised queue items (same shape as MOCK_QUEUE_BASE).
    Raises HTTPException on Pharmapi errors.
    """
    params: dict = {
        "page": page,
        "size": size,
    }
    if prescription_status:
        params["prescriptionStatus"] = prescription_status
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if barcode:
        params["barcode"] = barcode
    if amka:
        params["amka"] = amka

    raw = await pharmapi_get("/api/v1/prescriptions/search", params=params)
    if not isinstance(raw, dict) or "contents" not in raw:
        logger.warning(
            "Pharmapi search response missing 'contents' key; got keys=%s",
            list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
        )
    return _parse_prescription_search_json(raw.get("contents", []) if isinstance(raw, dict) else [])


# ── Patient search ──────────────────────────────────────────


def clean_pharmapi_patient_data(data: dict) -> PatientPayload:
    birthdate = datetime.strptime(data["dateOfBirth"], "%Y-%m-%d")
    # AMKA is the canonical id; EKAA is the European fallback for non-Greek patients.
    identifier = data.get("amka") or data.get("ekaa")
    if not identifier:
        raise HTTPException(502, "Pharmapi returned patient with no AMKA or EKAA")
    return PatientPayload(
        id=identifier,
        amka=data.get("amka") or None,
        ekaa=data.get("ekaa"),
        first_name=data["firstName"],
        last_name=data["lastName"],
        date_of_birth=data["dateOfBirth"],
        age=age_from_date(birthdate),
        sex=data["sex"],
        phone=data["mobile"],
        conditions=None,
        allergies=None,
        intolerances=None,
        safety_flags=None,
    )


async def pharmapi_get_patient(
    amka: str | None = None,
    ekaa: str | None = None,
) -> PatientPayload:
    """
    Fetch the patient's data from Pharmapi /api/v1/common/getpatient.
    Pass `amka` for Greek patients or `ekaa` for European-card patients;
    at least one must be provided.
    """
    if amka:
        params: dict = {"amka": amka}
    elif ekaa:
        params = {"ekaa": ekaa}
    else:
        # HTTPException here matches the rest of this service module
        # (pharmapi_get, verify_pharmapi_credentials, pharmapi_headers all
        # raise HTTPException directly). Migrating to ValueError + router
        # translation is a file-wide convention change, not scoped here
        # (PR #67 review #4).
        raise HTTPException(400, "pharmapi_get_patient requires amka or ekaa")
    patient_json = await pharmapi_get("/api/v1/common/getpatient", params=params)
    return clean_pharmapi_patient_data(patient_json)


async def pharmapi_get_masterdata_medicines(
    page: int = 0,
    size: int = 500,
    since: str | None = None,
) -> dict:
    """Fetch one page of the national medicine catalogue from Pharmapi.

    Uses /updates?since=YYYY-MM-DD when `since` is supplied — intended for
    nightly incremental refresh rather than a full re-download every session.
    Returns the raw paginated JSON: {"contents": [...], "lastPage": bool, ...}.
    """
    if os.getenv("PHARMAPI_MOCK", "false").lower() not in ("false", "0", "no"):
        return {"contents": [], "lastPage": True}

    if since:
        path = "/api/v1/masterdata/medicines/updates"
        params: dict = {"page": page, "size": size, "since": since}
    else:
        path = "/api/v1/masterdata/medicines"
        params = {"page": page, "size": size}

    return await pharmapi_get(path, params=params)
