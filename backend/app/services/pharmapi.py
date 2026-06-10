"""Pharmapi (ΗΔΥΚΑ) HTTP client + 24h session tracker.

In production the session state would live in Redis or a real DB; here it's
just a per-process dict so a `uvicorn --reload` reset clears it.

Two credential paths flow through this module (B2B Core BC-4):

* **Legacy / B2C** — every function called WITHOUT a ``ctx`` argument uses the
  module-level env credentials (PHARMAPI_USER/PASS/API_KEY) and the ``legacy``
  entry of the session store, exactly as before the refactor. Existing call
  sites are untouched.
* **Per-location / B2B** — callers pass a :class:`PharmapiContext` (built from
  a ``locations`` row by the /v1 API-key dependency). Basic Auth, the base
  URL, the Api-Key header, the ΗΔΥΚΑ pharmacy unit id, and the 24h session
  entry are all taken from the context, so every upstream call transacts under
  the calling location's own ΗΔΥΚΑ identity.
"""

import asyncio
import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from app.schemas.patients import ParticipationException, PatientPayload
from app.utils.dates import age_from_date

from ..config import get_settings
from ..constants import PrescriptionStatus
from ..utils.environment import is_mock_pharmapi_explicit

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

_PHARMAPI_RX_ERRORS: dict[str, tuple[int, str]] = {
    "G01": (404, "Prescription not found — verify barcode or AMKA"),
    "G02": (409, "Prescription already executed"),
    "G03": (409, "Prescription is cancelled — cannot execute"),
    "G04": (410, "Prescription is expired — check validity dates"),
    "G05": (422, "Patient insurance is invalid — verify coverage"),
    "G06": (422, "Partial execution not allowed for this prescription"),
    "G07": (404, "Medicine not found — verify barcode"),
}


# Session-store key for the legacy single-account (B2C) path.
LEGACY_SESSION_KEY = "legacy"


@dataclass(frozen=True)
class PharmapiContext:
    """Per-location upstream identity for a Pharmapi call (B2B /v1 path).

    ``username``/``password`` are the location's DECRYPTED ΗΔΥΚΑ Basic-Auth
    credentials — in-memory only, never logged, never persisted. ``api_key``
    is the vendor Api-Key (today shared app-wide per the ΗΔΥΚΑ registration;
    carried here so a per-location key becomes a data change, not a refactor).
    ``pharmacy_unit_id`` is the upstream unit id embedded in intolerance /
    medicine-history URLs. ``session_key`` keys the 24h session store entry
    (``location:<uuid>``).
    """

    username: str
    password: str
    api_key: str
    base_url: str
    pharmacy_unit_id: int | str | None
    session_key: str


def _blank_session() -> dict:
    return {
        "connected": False,
        "connected_at": None,  # ISO timestamp
        "connected_at_ts": 0.0,  # unix timestamp
        "user_data": None,  # response from /api/v1/user/me
        "pharmacy_id": None,  # units[0].id from /api/v1/user/me
    }


# In-memory 24h session tracker for the LEGACY (B2C) path. Mutated by
# /auth/login, /pharmapi/connect, the keepalive loop, and the G14 retry.
# Kept as a module-level dict (not folded into the store) because
# routers/pharmapi.py and scripts read it by name.
pharmapi_session: dict = _blank_session()


class PharmapiSessionStore:
    """In-process ΗΔΥΚΑ session tracker keyed by location (BC-4 / D-1).

    One entry per ``session_key`` (``legacy`` for B2C, ``location:<uuid>`` for
    B2B), each with a per-key asyncio.Lock serialising session establishment
    and the G14 refresh. The narrow get/lock/invalidate surface is the seam a
    Redis-backed implementation drops into later — callers never touch the
    dicts directly. Single-uvicorn-worker remains a deployment constraint
    until then (same as the legacy dict before this refactor).
    """

    def __init__(self) -> None:
        # The legacy entry IS the module-level dict (same object identity) so
        # existing direct readers/writers and the store always agree.
        self._sessions: dict[str, dict] = {LEGACY_SESSION_KEY: pharmapi_session}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, session_key: str) -> dict:
        return self._sessions.setdefault(session_key, _blank_session())

    def lock(self, session_key: str) -> asyncio.Lock:
        return self._locks.setdefault(session_key, asyncio.Lock())

    def invalidate(self, session_key: str) -> None:
        self._sessions[session_key] = (
            pharmapi_session if session_key == LEGACY_SESSION_KEY else _blank_session()
        )
        if session_key == LEGACY_SESSION_KEY:
            pharmapi_session.update(_blank_session())


_session_store = PharmapiSessionStore()


def session_is_valid(session_key: str = LEGACY_SESSION_KEY) -> bool:
    entry = _session_store.get(session_key)
    if not entry["connected"]:
        return False
    elapsed = time.time() - entry["connected_at_ts"]
    return elapsed < SESSION_WINDOW_SECONDS


def session_status() -> dict:
    """Snapshot of the 24h session tracker — shared by GET /pharmapi/status and
    the Settings "Refresh session" endpoint so both report identical shapes."""
    if not pharmapi_session["connected"]:
        return {
            "pharmapi_connected": False,
            "connected_at": None,
            "session_age_minutes": None,
            "session_valid_for_minutes": None,
            "pharmapi_user": None,
        }
    elapsed = time.time() - pharmapi_session["connected_at_ts"]
    remaining = max(0.0, SESSION_WINDOW_SECONDS - elapsed)
    return {
        "pharmapi_connected": session_is_valid(),
        "connected_at": pharmapi_session["connected_at"],
        "session_age_minutes": round(elapsed / 60, 1),
        "session_valid_for_minutes": round(remaining / 60, 1),
        "pharmapi_user": pharmapi_session["user_data"],
    }


KEEPALIVE_RETRY_SECONDS = 600  # back off ~10 min after a failed refresh


async def keepalive_loop(interval_seconds: int) -> None:
    """Proactively re-pin the ΗΔΥΚΑ session so it never lapses (>=1 /user/me per
    24h) even when the app is idle.

    Hits LIVE Pharmapi even in mock mode — keeping the real upstream session
    warm is the whole point (the seed and any live call depend on it). Failures
    are logged and retried, never fatal. Started/cancelled by the FastAPI
    lifespan and gated behind settings.pharmapi_keepalive_enabled (off in
    tests/CI so no unattended upstream calls).
    """
    logger.info("[Pharmapi] keep-alive loop started (every %ss)", interval_seconds)
    while True:
        try:
            profile = await verify_pharmapi_credentials(PHARMAPI_USER, PHARMAPI_PASS)
            _start_pharmapi_session(profile)
            logger.info("[Pharmapi] keep-alive: ΗΔΥΚΑ session refreshed")
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[Pharmapi] keep-alive loop stopped")
            raise
        except Exception as exc:
            logger.warning(
                "[Pharmapi] keep-alive refresh failed: %s — retrying in %ss",
                exc,
                KEEPALIVE_RETRY_SECONDS,
            )
            await asyncio.sleep(KEEPALIVE_RETRY_SECONDS)


def pharmapi_headers(ctx: PharmapiContext | None = None) -> dict:
    """Headers required on every Pharmapi call."""
    api_key = ctx.api_key if ctx is not None else PHARMAPI_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="PHARMAPI_API_KEY not set. Add it to your environment — it was in your ΗΔΥΚΑ registration email.",
        )
    return {
        "Accept": "application/json",
        "Api-Key": api_key,
    }


def _ctx_auth(ctx: PharmapiContext | None) -> tuple[str, str]:
    """Basic-Auth tuple for a call — the context's creds or the legacy env pair."""
    if ctx is not None:
        return (ctx.username, ctx.password)
    return (PHARMAPI_USER, PHARMAPI_PASS)


def _ctx_base(ctx: PharmapiContext | None) -> str:
    return ctx.base_url if ctx is not None else PHARMAPI_BASE


def _ctx_session_key(ctx: PharmapiContext | None) -> str:
    return ctx.session_key if ctx is not None else LEGACY_SESSION_KEY


async def ensure_pharmapi_session(ctx: PharmapiContext) -> None:
    """Open (or re-open) the 24h ΗΔΥΚΑ window for a B2B location, lazily.

    B2B API-key requests have no login moment, so the first call for a
    location (or the first after the 23h window lapses) establishes the
    session here. The per-key lock collapses concurrent establishment into
    one /user/me round-trip; ``_retrying=True`` stops the G14 branch from
    recursing back into session establishment.
    """
    async with _session_store.lock(ctx.session_key):
        if session_is_valid(ctx.session_key):
            return
        user_data = await pharmapi_get("/api/v1/user/me", _retrying=True, ctx=ctx)
        _start_pharmapi_session(user_data, session_key=ctx.session_key)


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
    _retrying: bool = False,
    ctx: PharmapiContext | None = None,
) -> dict | list:
    """Authenticated GET to Pharmapi. Raises HTTPException on failure.

    `params` is passed through to httpx so query-string values are properly
    URL-encoded. Callers MUST NOT pre-build a query string in `path` from
    untrusted input — pass them via `params` instead.

    Return type is `dict | list` because `r.json()` mirrors whatever the
    upstream returns — most endpoints return a paginated object, but
    `/api/v1/version` returns a top-level array. Callers are expected to
    narrow.

    `_retrying` is an internal flag — on a G14 (session expired) it auto-
    refreshes once via /user/me + _start_pharmapi_session and re-issues
    the original call. A second G14 raises 401 instead of looping.

    `ctx` selects the upstream identity: None → legacy env credentials +
    the legacy session (B2C, unchanged); a PharmapiContext → that location's
    credentials, base URL, Api-Key, and session entry (B2B /v1).
    """
    # B2B contexts establish their 24h window lazily — there is no login
    # moment. The legacy path keeps its existing semantics (login/connect
    # opens the window; the G14 branch below heals an expired one).
    if ctx is not None and not _retrying and not session_is_valid(ctx.session_key):
        await ensure_pharmapi_session(ctx)

    url = f"{_ctx_base(ctx)}{path}"
    headers = pharmapi_headers(ctx)
    if accept_xml:
        headers["Accept"] = "application/xml"
    logger.debug("[Pharmapi] GET %s params=%s", url, params)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            url,
            auth=_ctx_auth(ctx),
            headers=headers,
            params=params,
        )
    logger.debug("[Pharmapi] %s — %s", r.status_code, r.text[:500])

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

    # Full raw error for debugging — but bounded, because ΗΔΥΚΑ error bodies
    # can echo the request CDA (which carries patient AMKA + name) and we
    # don't want that landing in an HTTPException detail surfaced to the
    # browser. 200 chars is plenty for the G-code + Greek message; PHI lives
    # further down inside the structured CDA, well past byte 200.
    try:
        err_body = r.json()
        err = str(err_body)[:200]
    except Exception:
        err_body = {}
        err = r.text[:200]

    if "G12" in err:
        raise HTTPException(
            502, "Pharmapi: no active connection — call POST /pharmapi/connect first"
        )
    if "G14" in err or "914" in err or "Connection time limit" in err:
        if _retrying:
            raise HTTPException(401, "Pharmapi session expired — please re-login (G14)")
        # Re-auth with the SAME identity that made the failing call — the
        # per-key lock stops two concurrent G14s on one location from
        # double-refreshing (and one tenant's retry can never re-pin another
        # tenant's session entry).
        session_key = _ctx_session_key(ctx)
        try:
            async with _session_store.lock(session_key):
                user_data = await pharmapi_get("/api/v1/user/me", _retrying=True, ctx=ctx)
                _start_pharmapi_session(user_data, session_key=session_key)
        except Exception as exc:
            logger.warning("G14 auto-refresh failed: %s", exc)
            raise HTTPException(401, "Pharmapi session expired — please re-login (G14)") from exc
        return await pharmapi_get(
            path, accept_xml=accept_xml, params=params, _retrying=True, ctx=ctx
        )
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    for code, (status, message) in _PHARMAPI_RX_ERRORS.items():
        if re.search(rf"\b{re.escape(code)}\b", err):
            raise HTTPException(status, f"Pharmapi: {message} ({code})")
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
    logger.debug("[Pharmapi] AUTH %s as %s", url, username)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, auth=(username, password), headers=headers)
    logger.debug("[Pharmapi] %s — %s", r.status_code, r.text[:300])

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
    if is_mock_pharmapi_explicit():
        return {
            "email": f"{username}@pharmapi.local",
            "name": {"firstname": "Mock", "lastname": "Pharmacist"},
            "pharmacy": {"name": "Mock Pharmacy", "id": 0},
            "units": [{"id": 0, "name": "Mock Pharmacy"}],
        }
    return await verify_pharmapi_credentials(username, password)


def _start_pharmapi_session(user_data: dict, session_key: str = LEGACY_SESSION_KEY) -> None:
    """Pin the 24h connection window for one session entry.

    Legacy callers (/auth/login, /pharmapi/connect, keepalive) keep the
    default key and behave exactly as before; B2B callers pass their
    location's key so tenants never overwrite each other's window.
    """
    entry = _session_store.get(session_key)
    units = user_data.get("units", [])
    entry["pharmacy_id"] = units[0].get("id") if units else user_data.get("pharmacy", {}).get("id")
    entry.update(
        {
            "connected": True,
            "connected_at": datetime.now(UTC).isoformat(),
            "connected_at_ts": time.time(),
            "user_data": user_data,
        }
    )


def get_pharmacy_id(ctx: PharmapiContext | None = None) -> int | str:
    """ΗΔΥΚΑ pharmacy unit id for URL paths (intolerances / medicine history).

    B2B contexts carry the unit id on the `locations` row — no session
    needed. The legacy path keeps reading the session entry pinned at login
    (and keeps its existing 403/500 semantics).
    """
    if ctx is not None and ctx.pharmacy_unit_id is not None:
        return ctx.pharmacy_unit_id
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
        logger.warning("Pharmapi unmapped status '%s' — defaulting to UNKNOWN", pharmapi_status)
        return PrescriptionStatus.UNKNOWN
    return _PHARMAPI_STATUS_MAP[s]


# DEPRECATED — Pharmapi v2 returns JSON. Kept until confirmed safe to remove.
def parse_prescription_search_xml(xml_text: str) -> list[dict]:
    """
    Parse the XML response from GET /api/v1/prescriptions/search.

    Returns a list of normalised prescription queue items. Each item matches
    the shape expected by the /prescriptions dashboard (same as MOCK_QUEUE_BASE),
    with additional Pharmapi-specific fields preserved.

    Fields not present in the XML response (populated as None):
      - medication / drugName  → available in v2 JSON via medicines[0]["name"]
      - physician              → available in v2 JSON via doctorName
    Note: Pharmapi v2 has no per-prescription detail endpoint; use
    _parse_prescription_search_json for the current JSON-based path.
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
                "medication": None,  # not in XML — available in v2 JSON via medicines[0]["name"]
                "physician": None,  # not in XML — available in v2 JSON via doctorName
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
    """Call GET /api/v1/version and log the current API version at startup.

    Per the v2 OpenAPI spec /version returns a plain string (application/text
    or application/xml) — not the paginated JSON shape we originally assumed.
    We ask for XML and pull the version line out of the body.
    """
    try:
        data = await pharmapi_get("/api/v1/version", accept_xml=True)
        body = data.get("raw_xml", "") if isinstance(data, dict) else str(data)
        if body:
            # Body looks like: "## Πληροφορίες Εκδόσεων\n\n1.0.0\n\nRelease Gen2 PharmApi"
            # Just log the whole thing on one line — it's short and changes rarely.
            one_line = " | ".join(s.strip() for s in body.splitlines() if s.strip())
            logger.info("Pharmapi version: %s", one_line)
        else:
            logger.warning("Pharmapi /version returned empty body")
    except Exception as exc:
        logger.warning("Pharmapi version check failed — %s", exc)


# ── eDispensation POST (P3 — POST /prescriptions/{rx}/approve live wiring) ───
PHARMAPI_DISPENSE_PATH = "/api/v1/prescriptions/dispense"
# Spec: Accept: "application/x-hl7, application/xml", Content-Type: application/x-hl7.
PHARMAPI_HL7_CONTENT_TYPE = "application/x-hl7"
# Synthetic stub CDA used by the mock branch so dispense_log.response_cda has a
# non-empty value with the same outer shape ΗΔΥΚΑ would return. NOT a full CDA
# — it's the absolute minimum parse_dispense_response needs (executionNo +
# inFulfillmentOf barcode + effectiveTime) so callers can round-trip through
# the same envelope shape.
_MOCK_RESPONSE_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<ClinicalDocument xmlns="urn:hl7-org:v3">\n'
    '  <templateId root="1.3.6.1.4.1.12559.11.10.1.3.1.1.2"/>\n'
    '  <id extension="{barcode}" root="1.21"/>\n'
    '  <effectiveTime value="{effective_time}"/>\n'
    "  <inFulfillmentOf>\n"
    "    <order>\n"
    '      <id extension="{barcode}" root="1.21"/>\n'
    "    </order>\n"
    "  </inFulfillmentOf>\n"
    "  <component><structuredBody><component><section><entry><act>\n"
    '    <id extension="{exec_ref}" root="1.22"/>\n'
    "  </act></entry></section></component></structuredBody></component>\n"
    "</ClinicalDocument>\n"
)


def _mock_dispense_envelope(barcode: str) -> dict:
    """Mock-mode dispense response — same envelope shape as live."""
    # Imported lazily so cda.py (and lxml) stays optional for callers that
    # only need the search/patient surfaces in mock mode.
    from .cda import parse_dispense_response

    exec_ref = f"MOCK-EXEC-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(UTC)
    stub_xml = _MOCK_RESPONSE_TEMPLATE.format(
        barcode=barcode,
        effective_time=now.strftime("%Y%m%d%H%M%S"),
        exec_ref=exec_ref,
    )
    envelope = parse_dispense_response(stub_xml).to_envelope()
    envelope["response_cda"] = stub_xml
    return envelope


async def pharmapi_dispense(
    *,
    barcode: str,
    cda_xml: bytes,
    doctor_ip: str,
    ctx: PharmapiContext | None = None,
) -> dict:
    """POST an eDispensation CDA to ΗΔΥΚΑ and return the parsed receipt.

    Endpoint, headers, and body shape from the IDIKA spec
    (``info.description`` → ``## Εκτέλεση Συνταγής``):

      POST /api/v1/prescriptions/dispense
      Content-Type: application/x-hl7
      Accept: application/x-hl7, application/xml
      Api-Key: <pharmapi api key>
      X-DOCTOR-IP: <real external IP of the calling pharmacist>
      Authorization: Basic <pharmapi user:pass>

    Returns ``{exec_ref, executed_at, status, barcode, response_cda}`` —
    identical shape in mock and live mode so the router and dispense_log
    writer stay mode-blind. Raises HTTPException on upstream error; callers
    MUST NOT persist a success log on a raised exception.

    PHI guard: the request and response CDAs carry patient identifiers.
    They MUST NOT be logged here; the upstream status code + ΗΔΥΚΑ error
    code is safe.
    """
    if not doctor_ip:
        # X-DOCTOR-IP is mandatory per spec. Raise loudly rather than send
        # blank — ΗΔΥΚΑ may reject silently or log an unattributable call.
        raise HTTPException(500, "pharmapi_dispense: doctor_ip is required (X-DOCTOR-IP)")

    # FAIL-LIVE default (unset ⇒ live) — dispense is the most safety-critical
    # call in this module; rationale + the 3fcf012 history live on the helper.
    if is_mock_pharmapi_explicit():
        return _mock_dispense_envelope(barcode)

    # Imported here so the module's existing import-time cost stays unchanged
    # for the search/patient endpoints; cda is only needed in the live path.
    from .cda import parse_dispense_response

    url = f"{_ctx_base(ctx)}{PHARMAPI_DISPENSE_PATH}"
    headers = pharmapi_headers(ctx)
    headers["Accept"] = f"{PHARMAPI_HL7_CONTENT_TYPE}, application/xml"
    headers["Content-Type"] = PHARMAPI_HL7_CONTENT_TYPE
    headers["X-DOCTOR-IP"] = doctor_ip

    # Deliberately short log line — never the CDA body (PHI).
    logger.info(
        "[Pharmapi] POST %s barcode=%s doctor_ip=%s body_bytes=%d",
        url,
        barcode,
        doctor_ip,
        len(cda_xml),
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            auth=_ctx_auth(ctx),
            headers=headers,
            content=cda_xml,
        )

    if r.status_code == 200:
        try:
            parsed = parse_dispense_response(r.content)
        except ValueError as exc:
            raise HTTPException(502, f"Pharmapi: dispense response unparseable — {exc}") from exc
        envelope = parsed.to_envelope()
        envelope["response_cda"] = r.text
        return envelope

    err = _parse_pharmapi_error(r)
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(401, "Pharmapi session expired — please re-login (G14)")
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    for code, (status, message) in _PHARMAPI_RX_ERRORS.items():
        if re.search(rf"\b{re.escape(code)}\b", err):
            raise HTTPException(status, f"Pharmapi: {message} ({code})")
    if r.status_code == 401:
        raise HTTPException(502, f"Pharmapi: bad credentials — {err}")
    raise HTTPException(502, f"Pharmapi dispense error {r.status_code}: {err}")


async def pharmapi_get_prescription(
    *,
    barcode: str,
    pharmacy_id: int | str,
    doctor_ip: str,
    ctx: PharmapiContext | None = None,
) -> dict:
    """Barcode-direct retrieval — GET /api/v1/prescriptions/get/{barcode}.

    Spec: ΗΔΥΚΑ pharmapi v2 ``info.description`` → ``## Άντληση Συνταγής``.
    Returns the source prescription as an epSOS ePrescription CDA, parsed into
    the SAME dict shape ``pharmapi_search_prescriptions`` yields (so the resolve
    path, safety engine, and verification UI are unchanged) plus ``therapyLines``
    carrying the real per-line ids the eDispensation must echo.

    Unlike /search, this surfaces PAPERLESS (άυλη) prescriptions — the reason
    the scan-barcode flow resolves through here. ``pharmacyId`` is the upstream
    pharmacy unit (e.g. 70014); ``doctor_ip`` populates the mandatory
    X-DOCTOR-IP header (the calling pharmacist's external IP).

    PHI guard: the returned CDA carries patient AMKA + name. We never log the
    body — only the barcode + HTTP status.
    """
    if not doctor_ip:
        raise HTTPException(500, "pharmapi_get_prescription: doctor_ip is required (X-DOCTOR-IP)")

    from .cda import parse_prescription_cda

    url = f"{_ctx_base(ctx)}/api/v1/prescriptions/get/{barcode}"
    headers = pharmapi_headers(ctx)
    headers["Accept"] = f"{PHARMAPI_HL7_CONTENT_TYPE}, application/xml"
    headers["Content-Type"] = PHARMAPI_HL7_CONTENT_TYPE
    headers["X-DOCTOR-IP"] = doctor_ip

    logger.info("[Pharmapi] GET %s pharmacyId=%s", url, pharmacy_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            url,
            params={"pharmacyId": pharmacy_id},
            auth=_ctx_auth(ctx),
            headers=headers,
        )

    if r.status_code == 200:
        try:
            parsed = parse_prescription_cda(r.content)
        except Exception as exc:
            raise HTTPException(502, f"Pharmapi: prescription CDA unparseable — {exc}") from exc
        # Fail loudly when the CDA parsed but yielded no medicine lines — the
        # downstream eDispensation builder would otherwise produce a schema-
        # invalid (empty supply) CDA and ΗΔΥΚΑ would reject it with a less
        # diagnostic message than this 502.
        if not parsed.lines:
            raise HTTPException(
                502,
                f"Pharmapi: prescription {barcode} returned no medicine lines — "
                "upstream CDA missing substanceAdministration entries",
            )
        return parsed.to_rx_dict(status_mapper=_map_pharmapi_status)

    err = _parse_pharmapi_error(r)
    if "G14" in err or "914" in err or "Connection time limit" in err:
        raise HTTPException(401, "Pharmapi session expired — please re-login (G14)")
    if "G15" in err:
        raise HTTPException(500, "Pharmapi: Api-Key missing — set PHARMAPI_API_KEY env var")
    if "G11" in err:
        raise HTTPException(500, "Pharmapi: Api-Key invalid — check PHARMAPI_API_KEY value")
    for code, (status, message) in _PHARMAPI_RX_ERRORS.items():
        if re.search(rf"\b{re.escape(code)}\b", err):
            raise HTTPException(status, f"Pharmapi: {message} ({code})")
    if r.status_code == 404:
        raise HTTPException(404, f"Prescription {barcode} not found")
    if r.status_code == 401:
        raise HTTPException(502, f"Pharmapi: bad credentials — {err}")
    raise HTTPException(502, f"Pharmapi get-prescription error {r.status_code}: {err}")


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
                    # Surfaced for ATC lookup against drug_catalog (alerts dashboard).
                    "medicineBarcode": medicines[0].get("barcode") if medicines else None,
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
    prescribed: bool | None = None,
    page: int = 0,
    size: int = 50,
    from_date: str | None = None,
    to_date: str | None = None,
    barcode: str | None = None,
    amka: str | None = None,
    ctx: PharmapiContext | None = None,
) -> list[dict]:
    """
    Fetch the prescription queue (or a specific prescription) from Pharmapi.

    prescribed=False → pending (not-yet-dispensed) prescriptions
    prescribed=True  → already-dispensed prescriptions (NOTE: ΗΔΥΚΑ requires
                       `amka` alongside, else returns code 606)
    barcode=<code>   → find one specific prescription by barcode

    Returns a list of normalised queue items (same shape as MOCK_QUEUE_BASE).
    Raises HTTPException on Pharmapi errors.
    """
    params: dict = {
        "page": page,
        "size": size,
    }
    if prescribed is not None:
        params["prescribed"] = str(prescribed).lower()
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if barcode:
        params["barcode"] = barcode
    if amka:
        params["amka"] = amka

    raw = await pharmapi_get("/api/v1/prescriptions/search", params=params, ctx=ctx)
    if not isinstance(raw, dict) or "contents" not in raw:
        logger.warning(
            "Pharmapi search response missing 'contents' key; got keys=%s",
            list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
        )
    return _parse_prescription_search_json(raw.get("contents", []) if isinstance(raw, dict) else [])


# ── Patient search ──────────────────────────────────────────


def clean_pharmapi_patient_data(data: dict) -> PatientPayload:
    # Pharmapi v2 uses "birthDate" (spec-confirmed). The old PDF reference doc
    # incorrectly listed "dateOfBirth" — do not revert.
    birth_date_str = data["birthDate"]
    birthdate = datetime.strptime(birth_date_str, "%Y-%m-%d")
    # AMKA is the canonical id; EKAA is the European fallback for non-Greek patients.
    identifier = data.get("amka") or data.get("identificationNo")
    if not identifier:
        raise HTTPException(502, "Pharmapi returned patient with no AMKA or EKAA")
    # Co-pay exemption records (FT-2 / D-9): None when upstream omits the key,
    # [] when present-but-empty — callers can tell "not supplied" from "none".
    part_exceptions = data.get("patientPartExceptions")
    participation_exceptions = (
        [
            ParticipationException(
                id=e.get("id"),
                reason=e.get("exceptionReason"),
                effective_from=e.get("effectiveFrom"),
                effective_to=e.get("effectiveTo"),
            )
            for e in part_exceptions
        ]
        if part_exceptions is not None
        else None
    )
    return PatientPayload(
        id=identifier,
        amka=data.get("amka") or None,
        ekaa=data.get("identificationNo"),  # European patients use identificationNo
        first_name=data["firstName"],
        last_name=data["lastName"],
        date_of_birth=birth_date_str,
        age=age_from_date(birthdate),
        sex=data.get("sex", {}).get("name", "")
        if isinstance(data.get("sex"), dict)
        else data.get("sex") or "",
        phone=data.get("telephone") or "",
        nationality=data.get("nationality") or None,
        address=data.get("address") or None,
        email=None,
        conditions=None,
        allergies=None,
        intolerances=None,
        safety_flags=None,
        participation_exceptions=participation_exceptions,
    )


async def pharmapi_get_patient(
    amka: str | None = None,
    ekaa: str | None = None,
    ctx: PharmapiContext | None = None,
) -> PatientPayload:
    """
    Fetch the patient's data from Pharmapi /api/v1/common/getpatient.
    Pass `amka` for Greek patients or `ekaa` for European-card patients;
    at least one must be provided.
    """
    if amka:
        params: dict = {"patientamka": amka}
    elif ekaa:
        params: dict = {"patientekaa": ekaa}
    else:
        # HTTPException here matches the rest of this service module
        # (pharmapi_get, verify_pharmapi_credentials, pharmapi_headers all
        # raise HTTPException directly). Migrating to ValueError + router
        # translation is a file-wide convention change, not scoped here
        # (PR #67 review #4).
        raise HTTPException(400, "pharmapi_get_patient requires amka or ekaa")
    patient_json = await pharmapi_get("/api/v1/common/getpatient", params=params, ctx=ctx)
    return clean_pharmapi_patient_data(patient_json)


async def pharmapi_get_patient_insurances(
    amka: str | None = None,
    ekaa: str | None = None,
    ctx: PharmapiContext | None = None,
) -> list[dict]:
    if amka:
        params: dict = {"patientamka": amka}
    elif ekaa:
        params: dict = {"patientekaa": ekaa}
    else:
        raise HTTPException(400, "pharmapi_get_patient_insurances requires amka or ekaa")
    result = await pharmapi_get("/api/v1/common/getpatient/insurances", params=params, ctx=ctx)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        contents = result.get("contents")
        if isinstance(contents, list):
            return contents
    logger.warning(
        "[Pharmapi] /getpatient/insurances returned unexpected shape: %s", type(result).__name__
    )
    return []


def _parse_page_xml(raw_xml: str) -> dict:
    """Parse a paginated XML response, returning items and page metadata.

    Extracts the standard Pharmapi pagination envelope fields (totalPages,
    lastPage, totalEntries) from root-level elements alongside the item list.
    Falls back to safe defaults if any field is absent or non-numeric.
    """
    if not raw_xml:
        return {"items": [], "totalPages": 1, "lastPage": True, "totalEntries": 0}
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise HTTPException(502, f"Pharmapi: could not parse XML page response — {exc}") from exc
    items = [{child.tag: child.text for child in item} for item in root.findall("./contents/item")]

    def _root_text(tag: str) -> str | None:
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else None

    try:
        total_pages = int(_root_text("totalPages") or 1)
    except ValueError:
        total_pages = 1
    try:
        total_entries = int(_root_text("totalEntries") or len(items))
    except ValueError:
        total_entries = len(items)

    return {
        "items": items,
        "totalPages": total_pages,
        "lastPage": (_root_text("lastPage") or "true").lower() == "true",
        "totalEntries": total_entries,
    }


def _parse_page_xml_items(raw_xml: str) -> list[dict]:
    return _parse_page_xml(raw_xml)["items"]


async def pharmapi_get_patient_intolerances(
    amka_or_ekaa: str,
    ctx: PharmapiContext | None = None,
) -> list[dict]:
    pharmacy_id = get_pharmacy_id(ctx)
    # Spec ref: GET /patients/{amkaOrEkaa}/medicinehistory/{pharmacyId}/intolerances
    # exposes `patientsConsent` as an optional query flag. Without it, ΗΔΥΚΑ
    # blocks every call with code 608 "Patient's consent is required for full
    # history." Asserting consent here matches our UX assumption that the
    # pharmacist already obtained consent at the counter. The /v1 B2B surface
    # only reaches this after the caller attested consent explicitly (D-5).
    raw = await pharmapi_get(
        f"/api/v1/patients/{amka_or_ekaa}/medicinehistory/{pharmacy_id}/intolerances",
        accept_xml=True,
        params={"patientsConsent": "true"},
        ctx=ctx,
    )
    return _parse_page_xml_items(raw.get("raw_xml", ""))


async def pharmapi_get_patient_medicine_history(
    amka_or_ekaa: str,
    page: int = 0,
    size: int = 50,
    ctx: PharmapiContext | None = None,
) -> dict:
    """Fetch one page of executed prescription history for a patient.

    Returns {"items": [...], "totalPages": N, "lastPage": bool,
             "totalEntries": N, "blocked": False}.

    On error 609 (pharmacy not yet permissioned by ΗΔΥΚΑ) returns the same
    shape with empty items and "blocked": True so callers can render a
    graceful empty state rather than propagating an error.
    """
    pharmacy_id = get_pharmacy_id(ctx)
    # See note on pharmapi_get_patient_intolerances re: patientsConsent.
    try:
        raw = await pharmapi_get(
            f"/api/v1/patients/{amka_or_ekaa}/medicinehistory/full/{pharmacy_id}/prescription",
            accept_xml=True,
            params={"patientsConsent": "true", "page": page, "size": size},
            ctx=ctx,
        )
    except HTTPException as exc:
        if "609" in str(exc.detail):
            return {
                "items": [],
                "totalPages": 1,
                "lastPage": True,
                "totalEntries": 0,
                "blocked": True,
            }
        raise
    return {**_parse_page_xml(raw.get("raw_xml", "")), "blocked": False}


async def pharmapi_get_masterdata_medicines(
    page: int = 0,
    size: int = 500,
    since: str | None = None,
    ctx: PharmapiContext | None = None,
) -> dict:
    """Fetch one page of the national medicine catalogue from Pharmapi.

    Uses /updates?since=YYYY-MM-DD when `since` is supplied — intended for
    nightly incremental refresh rather than a full re-download every session.
    Returns the raw paginated JSON: {"contents": [...], "lastPage": bool, ...}.
    """
    if is_mock_pharmapi_explicit():  # FAIL-LIVE default — see the helper's docstring
        return {"contents": [], "lastPage": True}

    if since:
        path = "/api/v1/masterdata/medicines/updates"
        params: dict = {"page": page, "size": size, "since": since}
    else:
        path = "/api/v1/masterdata/medicines"
        params = {"page": page, "size": size}

    return await pharmapi_get(path, params=params, ctx=ctx)


async def pharmapi_get_error_codes() -> list[dict]:
    try:
        result = await pharmapi_get("/api/v1/errorslist")
    except HTTPException:
        logger.info("pharmapi_get_error_codes: upstream unavailable — returning local error codes")
        return [{"code": k, "status": s, "message": m} for k, (s, m) in _PHARMAPI_RX_ERRORS.items()]

    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        content = result.get("contents")
        if content is None:
            logger.warning(
                "pharmapi_get_error_codes: unexpected response shape — keys: %s",
                list(result.keys()),
            )
            raise HTTPException(502, "Pharmapi: /api/v1/errorslist returned unexpected shape")
        return content
    raise HTTPException(
        502, f"Pharmapi: /api/v1/errorslist returned unexpected type {type(result).__name__}"
    )
