"""Pharmapi (ΗΔΥΚΑ) HTTP client + 24h session tracker.

In production the session state would live in Redis or a real DB; here it's
just a per-process dict so a `uvicorn --reload` reset clears it.
"""

import os
import time

import httpx
from fastapi import HTTPException


PHARMAPI_BASE    = os.getenv("PHARMAPI_BASE", "https://testeps.e-prescription.gr/pharmapiv2")
PHARMAPI_USER    = os.getenv("PHARMAPI_USERNAME", "medcare1pharmapi")
PHARMAPI_PASS    = os.getenv("PHARMAPI_PASSWORD", "Aa900919081908!!")
PHARMAPI_API_KEY = os.getenv("PHARMAPI_API_KEY", "pi2jwygkd07yho3a4dw6jc55tg5ra3uc")

SESSION_WINDOW_SECONDS = 23 * 3600  # 23h (refresh before 24h hard limit)


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
