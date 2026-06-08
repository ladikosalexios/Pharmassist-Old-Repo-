"""HMVS (ΗΔΥΚΑ / EU-FMD) pack-verification proxy — the backend behind
``frontend/src/lib/hmvs.ts``.

Exposes exactly the dispense-driven surface from ``docs/hmvs-scope.md``:

  verify        GET   /pharmapi/hmvs/product/gs1/{gtin}/pack/{serial}?batch=&expiry=
  state change  PATCH (same URL)  body { "state": "Supplied" | "Active" }

Both branch on ``HMVS_MOCK`` inside the service layer, audit via
``app/services/audit.py``, and resolve OAuth2 client-credentials per pharmacy
(env fallback to the ITE shared creds). The PATCH runs through the idempotency
guard so a timed-out supply cannot double-supply.
"""

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.pharmacist_pharmacy import PharmacistPharmacy
from ..db.session import get_session
from ..deps import get_current_user
from ..services import hmvs
from ..services.audit import fire_hmvs_audit
from ..services.hmvs import HmvsResult
from ..services.hmvs_credentials import resolve_hmvs_credentials
from ..utils.environment import is_mock_hmvs

router = APIRouter(prefix="/pharmapi/hmvs", tags=["hmvs"])

_VALID_STATES = {hmvs.STATE_ACTIVE, hmvs.STATE_SUPPLIED}


class StateChangeBody(BaseModel):
    state: str

    @field_validator("state")
    @classmethod
    def _known_state(cls, v: str) -> str:
        if v not in _VALID_STATES:
            raise ValueError(f"state must be one of {sorted(_VALID_STATES)}")
        return v


def _body(result: HmvsResult, gtin: str, serial: str) -> dict:
    """JSON shape returned to the frontend gateway (success and error detail)."""
    return {
        "ok": result.ok,
        "state": result.state,
        "currentState": result.current_state,
        "gtin": gtin,
        "serial": serial,
        "operationCode": result.operation_code,
        "nhrn": result.nhrn,
        "isIntermarket": result.is_intermarket,
        "information": result.information,
        "warning": result.warning,
        "alertId": result.alert_id,
        "queued": result.queued,
        # Throttle hint from a 429 Retry-After (seconds). None for any other
        # response — the FE shows a "retry in N seconds" affordance when set.
        "retryAfterSeconds": result.retry_after_seconds,
    }


async def _resolve_credentials(db: AsyncSession, pharmacist_id: str) -> tuple[str, str]:
    """ITE creds for this pharmacist's default pharmacy link (env fallback).

    Skipped entirely in mock mode — the service never fetches a token there, so
    an absent dev cred set must not 503 the call."""
    if is_mock_hmvs():
        return "", ""
    link = await db.scalar(
        select(PharmacistPharmacy).where(
            PharmacistPharmacy.pharmacist_id == uuid.UUID(pharmacist_id),
            PharmacistPharmacy.is_default.is_(True),
        )
    )
    try:
        return resolve_hmvs_credentials(link)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/product/gs1/{gtin}/pack/{serial}")
async def verify_pack(
    gtin: str,
    serial: str,
    batch: str = Query(..., description="Batch / lot number, GS1 (10)"),
    expiry: str | None = Query(None, description="Expiry YYMMDD, GS1 (17)"),
    current: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Confirm a scanned pack is genuine/active in the HMVS registry."""
    client_id, client_secret = await _resolve_credentials(db, current["pharmacist_id"])
    path = f"/pharmapi/hmvs/product/gs1/{gtin}/pack/{serial}"
    try:
        result = await hmvs.verify(
            gtin, serial, batch, expiry, client_id=client_id, client_secret=client_secret
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise HTTPException(status_code=504, detail="HMVS registry unreachable") from exc
    except httpx.HTTPStatusError as exc:
        # OAuth2 token endpoint refused the IDP creds (typically 401/403). Without
        # this branch the failure surfaced as an opaque 500 with no audit row —
        # the dispense was silently un-attributable. Map to 502 (upstream rejected
        # us) and still write the audit row so inspectors see the attempt.
        fire_hmvs_audit(
            pharmacist_id=uuid.UUID(current["pharmacist_id"]),
            pharmacy_id=uuid.UUID(current["pharmacy_id"]),
            action="HMVS_VERIFIED",
            resource_id=serial,
            pharmapi_path=path,
            pharmapi_status=502,
        )
        raise HTTPException(status_code=502, detail="HMVS auth failed") from exc

    fire_hmvs_audit(
        pharmacist_id=uuid.UUID(current["pharmacist_id"]),
        pharmacy_id=uuid.UUID(current["pharmacy_id"]),
        action="HMVS_VERIFIED",
        resource_id=serial,  # serial only — never the full QR
        pharmapi_path=path,
        pharmapi_status=result.http_status,
    )
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=_body(result, gtin, serial))
    return _body(result, gtin, serial)


@router.patch("/product/gs1/{gtin}/pack/{serial}")
async def change_pack_state(
    gtin: str,
    serial: str,
    body: StateChangeBody,
    batch: str = Query(..., description="Batch / lot number, GS1 (10)"),
    expiry: str | None = Query(None, description="Expiry YYMMDD, GS1 (17)"),
    current: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Supply (decommission) a pack on dispense, or reactivate to reverse it.

    Routed through the idempotency guard: a repeated identical state change
    returns the recorded result without issuing a second upstream PATCH, so a
    client retry after a timeout cannot double-supply.
    """
    client_id, client_secret = await _resolve_credentials(db, current["pharmacist_id"])
    path = f"/pharmapi/hmvs/product/gs1/{gtin}/pack/{serial}"
    action = "HMVS_DECOMMISSIONED" if body.state == hmvs.STATE_SUPPLIED else "HMVS_REACTIVATED"
    try:
        result = await hmvs.change_state_idempotent(
            db,
            pharmacist_id=uuid.UUID(current["pharmacist_id"]),
            pharmacy_id=uuid.UUID(current["pharmacy_id"]),
            gtin=gtin,
            serial=serial,
            batch=batch,
            expiry=expiry,
            target_state=body.state,
            client_id=client_id,
            client_secret=client_secret,
        )
    except httpx.HTTPStatusError as exc:
        # Token-endpoint refusal during a state change. Mirrors verify_pack: 502
        # with an audit row, never an opaque 500 — a failed decommission attempt
        # has to be inspector-visible.
        fire_hmvs_audit(
            pharmacist_id=uuid.UUID(current["pharmacist_id"]),
            pharmacy_id=uuid.UUID(current["pharmacy_id"]),
            action=action,
            resource_id=serial,
            pharmapi_path=path,
            pharmapi_status=502,
        )
        raise HTTPException(status_code=502, detail="HMVS auth failed") from exc

    fire_hmvs_audit(
        pharmacist_id=uuid.UUID(current["pharmacist_id"]),
        pharmacy_id=uuid.UUID(current["pharmacy_id"]),
        action=action,
        resource_id=serial,
        pharmapi_path=path,
        pharmapi_status=result.http_status,
    )

    # Store-and-forward: persisted but not yet confirmed upstream → 202 Accepted.
    if result.queued:
        return JSONResponse(status_code=202, content=_body(result, gtin, serial))
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=_body(result, gtin, serial))
    return _body(result, gtin, serial)
