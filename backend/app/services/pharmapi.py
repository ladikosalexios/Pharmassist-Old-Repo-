"""Pharmapi (ΗΔΥΚΑ) HTTP client + 24h session tracker.

In production the session state would live in Redis or a real DB; here it's
just a per-process dict so a `uvicorn --reload` reset clears it.

Pharmapi credentials are sourced from the centralised settings.
"""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException

from ..config import get_settings


# Module-level constants kept for backward compat — anything that imports
# these by name keeps working. Sourced from settings at first import.
_settings = get_settings()
PHARMAPI_BASE    = _settings.pharmapi_base
PHARMAPI_USER    = _settings.pharmapi_username
PHARMAPI_PASS    = _settings.pharmapi_password
PHARMAPI_API_KEY = _settings.pharmapi_api_key
SESSION_WINDOW_SECONDS = _settings.pharmapi_session_window_seconds


# In-memory 24h session tracker. Mutated by the /pharmapi/connect handler.
pharmapi_session: dict = {
    "connected": False,
    "connected_at": None,    # ISO timestamp
    "connected_at_ts": 0.0,  # unix timestamp
    "user_data": None,       # response from /api/v1user/me
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


async def pharmapi_get(path: str, accept_xml: bool = False) -> dict:
    """Authenticated GET to Pharmapi. Raises HTTPException on failure."""
    url = f"{PHARMAPI_BASE}{path}"
    headers = pharmapi_headers()
    if accept_xml:
        headers["Accept"] = "application/xml"
    print(f"[Pharmapi] GET {url}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            url,
            auth=(PHARMAPI_USER, PHARMAPI_PASS),
            headers=headers,
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
        raise HTTPException(502, "Pharmapi: no active connection — call POST /pharmapi/connect first")
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(502, "Pharmapi: 24h session expired — log into https://test.e-prescription.gr/epregen2/ first, then retry")
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
        except Exception:
            raise HTTPException(502, "Pharmapi: /user/me did not return JSON")

    err = _parse_pharmapi_error(r)
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(502, "Pharmapi: 24h session expired — log into https://test.e-prescription.gr/epregen2/ first, then retry")
    if r.status_code == 401:
        raise HTTPException(401, "Invalid Pharmapi credentials")
    raise HTTPException(502, f"Pharmapi error {r.status_code}: {err}")


def _start_pharmapi_session(user_data: dict) -> None:
    """Pin the 24h connection window — shared by /auth/login and /pharmapi/connect."""
    now = time.time()
    pharmapi_session.update({
        "connected": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "connected_at_ts": now,
        "user_data": user_data,
    })


# ── Prescription search XML parser ──────────────────────────────────────────

def _el(parent: ET.Element, tag: str) -> Optional[str]:
    """Safe text extraction from an XML element."""
    el = parent.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _date(raw: Optional[str]) -> Optional[str]:
    """Trim 'YYYY-MM-DD HH:MM:SS' → 'YYYY-MM-DD'."""
    if not raw:
        return None
    return raw.strip()[:10]


def _map_pharmapi_status(pharmapi_status: Optional[str]) -> str:
    """
    Map ΗΔΥΚΑ prescription status string to our internal status.

    NOTE: The exact status strings Pharmapi uses are unknown until a real
    prescription is fetched. Update this map when real values are seen.
    Known so far: the status object has {id, status} — we map the string.
    """
    if not pharmapi_status:
        return "PENDING"
    s = pharmapi_status.upper().strip()
    mapping = {
        "PENDING":    "PENDING",
        "ACTIVE":     "PENDING",     # assume active = awaiting dispense
        "COMPLETED":  "COMPLETED",
        "EXECUTED":   "COMPLETED",
        "CANCELLED":  "FLAGGED",
        "EXPIRED":    "FLAGGED",
        "PARTIAL":    "PENDING",     # partially dispensed — still actionable
    }
    return mapping.get(s, "PENDING")


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
        raise HTTPException(502, f"Pharmapi: could not parse prescription XML — {exc}")

    items = []
    for item in root.findall(".//contents/item"):
        patient = item.find("patientInfo")
        status_el = item.find("status")
        insurance_el = item.find("socialInsurance")

        amka = _el(patient, "amka") if patient is not None else None
        first_name = _el(patient, "firstName") if patient is not None else ""
        last_name = _el(patient, "lastName") if patient is not None else ""
        patient_name = f"{first_name} {last_name}".strip() or "Άγνωστος"

        pharmapi_status = _el(status_el, "status") if status_el is not None else None

        items.append({
            # ── Core fields (same shape as MOCK_QUEUE_BASE) ─────────────────
            "rxId":        _el(item, "barcode"),
            "patientName": patient_name,
            "medication":  None,   # not in search — populated on detail fetch
            "physician":   None,   # not in search — populated on detail fetch
            "date":        _date(_el(item, "issueDate")),
            "status":      _map_pharmapi_status(pharmapi_status),

            # ── Extra Pharmapi fields (useful for UI / filtering) ────────────
            "patientAmka":           amka,
            "expiryDate":            _date(_el(item, "expiryDate")),
            "executions":            _el(item, "executions"),
            "medicineDrug":          _el(item, "medicineDrug") == "true",
            "socialInsurance":       (
                _el(patient, "socialInsuranceShortName") if patient is not None
                else (_el(insurance_el, "shortName") if insurance_el is not None else None)
            ),
            "pharmApiStatus":        pharmapi_status,   # raw value for debugging
        })

    return items


async def pharmapi_search_prescriptions(
    prescribed: bool = False,
    page: int = 0,
    size: int = 50,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    barcode: Optional[str] = None,
    amka: Optional[str] = None,
) -> list[dict]:
    """
    Fetch the prescription queue (or a specific prescription) from Pharmapi.

    prescribed=False  → pending prescriptions (the dashboard queue)
    prescribed=True   → already-dispensed prescriptions (history)
    barcode=<code>    → find one specific prescription by barcode

    Returns a list of normalised queue items (same shape as MOCK_QUEUE_BASE).
    Raises HTTPException on Pharmapi errors.
    """
    params: list[str] = [
        f"page={page}",
        f"size={size}",
        f"prescribed={str(prescribed).lower()}",
    ]
    if from_date:
        params.append(f"from={from_date}")
    if to_date:
        params.append(f"to={to_date}")
    if barcode:
        params.append(f"barcode={barcode}")
    if amka:
        params.append(f"amka={amka}")

    raw = await pharmapi_get(f"/api/v1/prescriptions/search?{'&'.join(params)}", accept_xml=True)
    return parse_prescription_search_xml(raw.get("raw_xml", ""))
