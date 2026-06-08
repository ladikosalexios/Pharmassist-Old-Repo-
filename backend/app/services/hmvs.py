"""HMVS (Hellenic Medicines Verification System / EU-FMD) HTTP client.

Mirrors ``services/pharmapi.py`` in shape and conventions, but the upstream is
the NMVO ITE sandbox and auth is OAuth2 **client-credentials** (a cached Bearer
token) rather than Basic-Auth + Api-Key.

Surface (all driven by the pack a pharmacist scans at dispense — see
``docs/hmvs-scope.md``):

  verify        GET   {verification}/product/gs1/{gtin}/pack/{serial}?batch=&expiry=
  state change  PATCH (same URL)  body { "state": "Supplied" | "Active" }

Two robustness layers wrap the PATCH (``change_state_idempotent``):
  • **idempotency guard** — a UNIQUE row per (pack, target-state) means a retried
    or timed-out supply returns the recorded result instead of issuing a second
    upstream PATCH, so a timeout cannot double-supply;
  • **store-and-forward** — on a timeout/transport error or a 429 throttle the
    intent stays ``pending`` for ``replay_pending`` to re-issue later.

HMVS_MOCK (default true) short-circuits everything to canned ITE-style results —
no token fetch, no network — exactly like ``is_mock_pharmapi`` for Pharmapi.

Classification is driven off HTTP status + response **structure** (operationCode /
information / warning / alertId), never a hardcoded operation-code list — ITE adds
and retires codes.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models.hmvs_operation import HmvsOperation
from ..utils.environment import is_mock_hmvs

logger = logging.getLogger(__name__)

HMVS_TIMEOUT = httpx.Timeout(15.0)

# Lifecycle states relevant to dispense (EMVS/HMVS subset).
STATE_ACTIVE = "Active"
STATE_SUPPLIED = "Supplied"

# Per-client_id Bearer-token cache. Keyed by client_id so per-pharmacy IQE
# equipment creds (later) never share a token with the ITE shared creds.
_token_cache: dict[str, dict] = {}

# Test seam: when set, every AsyncClient is built with this transport so tests
# inject an httpx.MockTransport without monkeypatching the module. None → real
# network (the default in dev/prod live mode).
_transport_override: httpx.BaseTransport | None = None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HMVS_TIMEOUT, transport=_transport_override)


# ── Typed result ────────────────────────────────────────────────────────────


@dataclass
class HmvsResult:
    """Normalised outcome of a verify / state-change call.

    ``ok`` is the single signal the router maps to 2xx; everything else is
    surfaced verbatim so the UI can classify off the structure. ``queued`` marks
    the store-and-forward path (timeout/429) where the intent was persisted but
    not yet confirmed upstream.
    """

    ok: bool
    http_status: int
    operation_code: str | None = None
    state: str | None = None
    current_state: str | None = None  # 409 invalid-transition echoes current state
    nhrn: str | None = None
    is_intermarket: bool | None = None
    alert_id: str | None = None
    information: str | None = None
    warning: str | None = None
    queued: bool = False
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_cached(cls, op: HmvsOperation) -> HmvsResult:
        """Rebuild the result of an already-``completed`` operation from its row."""
        snapshot = op.response_json or {}
        # response_json was written by to_dict(), so it round-trips field-for-field.
        if "ok" in snapshot:
            return cls(**snapshot)
        # Defensive fallback if a row predates the snapshot column.
        return cls(
            ok=True,
            http_status=200,
            operation_code=op.operation_code,
            state=op.target_state,
            raw=snapshot,
        )


def _map_response(r: httpx.Response) -> HmvsResult:
    """Map an upstream HTTP response to an HmvsResult by status + body structure."""
    try:
        body = r.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    base = dict(
        operation_code=body.get("operationCode"),
        nhrn=body.get("nhrn"),
        is_intermarket=body.get("isIntermarket"),
        alert_id=body.get("alertId"),
        information=body.get("information"),
        warning=body.get("warning"),
        raw=body,
    )

    if r.status_code == 200:
        return HmvsResult(ok=True, http_status=200, state=body.get("state"), **base)
    if r.status_code == 409:
        # Invalid transition — the registry returns the pack's current state.
        return HmvsResult(ok=False, http_status=409, current_state=body.get("state"), **base)
    # 403 / 404 (incl. batch/expiry mismatch) / 422 / 429 / anything else: not ok.
    # 429 specifically is a throttle the caller should back off / queue on.
    return HmvsResult(ok=False, http_status=r.status_code, state=body.get("state"), **base)


# ── OAuth2 client-credentials token ─────────────────────────────────────────


async def _get_token(client_id: str, client_secret: str) -> str:
    """Return a cached Bearer access token, refreshing within the skew window."""
    settings = get_settings()
    cached = _token_cache.get(client_id)
    now = time.time()
    if cached and now < cached["expires_at_ts"] - settings.hmvs_token_skew_seconds:
        return cached["access_token"]

    url = f"{settings.hmvs_identity_url}/identity/connect/token"
    async with _client() as client:
        r = await client.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
    if r.status_code != 200:
        # Never echo the form body (carries the secret) into the error.
        raise httpx.HTTPStatusError(
            f"HMVS token endpoint returned {r.status_code}", request=r.request, response=r
        )
    payload = r.json()
    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _token_cache[client_id] = {"access_token": token, "expires_at_ts": now + expires_in}
    logger.info("[HMVS] OAuth2 token refreshed (expires in %ss)", expires_in)
    return token


def hmvs_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _pack_url(gtin: str, serial: str) -> str:
    settings = get_settings()
    return f"{settings.hmvs_verification_url}/product/gs1/{gtin}/pack/{serial}"


# ── Verify / state-change ────────────────────────────────────────────────────


async def verify(
    gtin: str,
    serial: str,
    batch: str,
    expiry: str | None,
    *,
    client_id: str,
    client_secret: str,
) -> HmvsResult:
    """GET the pack from the registry to confirm it is genuine/active."""
    if is_mock_hmvs():
        return _mock_verify(serial)
    token = await _get_token(client_id, client_secret)
    async with _client() as client:
        r = await client.get(
            _pack_url(gtin, serial),
            headers=hmvs_headers(token),
            params={"batch": batch, "expiry": expiry},
        )
    return _map_response(r)


async def change_state(
    gtin: str,
    serial: str,
    batch: str,
    expiry: str | None,
    *,
    target_state: str,
    client_id: str,
    client_secret: str,
) -> HmvsResult:
    """PATCH the pack to a new state (Supplied on dispense, Active to reverse)."""
    if is_mock_hmvs():
        return _mock_change_state(serial, target_state)
    token = await _get_token(client_id, client_secret)
    async with _client() as client:
        r = await client.patch(
            _pack_url(gtin, serial),
            headers=hmvs_headers(token),
            params={"batch": batch, "expiry": expiry},
            json={"state": target_state},
        )
    return _map_response(r)


# ── Idempotency guard + store-and-forward ────────────────────────────────────


def make_idempotency_key(gtin: str, serial: str, batch: str, target_state: str) -> str:
    """Deterministic key so a retried PATCH hashes to the same row."""
    return f"{gtin}:{serial}:{batch}:{target_state}"


async def change_state_idempotent(
    session: AsyncSession,
    *,
    pharmacist_id: uuid.UUID,
    pharmacy_id: uuid.UUID,
    gtin: str,
    serial: str,
    batch: str,
    expiry: str | None,
    target_state: str,
    client_id: str,
    client_secret: str,
) -> HmvsResult:
    """``change_state`` wrapped in the double-supply guard + store-and-forward.

    A previously-``completed`` intent short-circuits to its cached result with no
    upstream call. A timeout/transport error or 429 leaves the row ``pending`` for
    ``replay_pending`` and returns a ``queued`` result.
    """
    key = make_idempotency_key(gtin, serial, batch, target_state)

    # Get-or-create the pending row. The UNIQUE idempotency_key is the real
    # guard: if a concurrent identical PATCH wins the insert race, our flush
    # raises IntegrityError and we reload the winner instead of double-inserting.
    op = await session.scalar(select(HmvsOperation).where(HmvsOperation.idempotency_key == key))
    if op is None:
        op = HmvsOperation(
            idempotency_key=key,
            pharmacist_id=pharmacist_id,
            pharmacy_id=pharmacy_id,
            gtin=gtin,
            serial=serial,
            batch=batch,
            expiry=expiry,
            target_state=target_state,
            status="pending",
        )
        session.add(op)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            op = await session.scalar(
                select(HmvsOperation).where(HmvsOperation.idempotency_key == key)
            )

    # Double-supply guard: a completed intent never re-hits the registry.
    if op.status == "completed":
        logger.info("[HMVS] idempotent hit — returning cached result for %s", key)
        return HmvsResult.from_cached(op)

    op.attempts = (op.attempts or 0) + 1
    try:
        result = await change_state(
            gtin,
            serial,
            batch,
            expiry,
            target_state=target_state,
            client_id=client_id,
            client_secret=client_secret,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        # Store-and-forward: keep the intent for replay; surface as queued.
        logger.warning("[HMVS] %s — intent %s queued for replay", exc, key)
        op.status = "pending"
        await session.commit()
        return HmvsResult(ok=False, http_status=504, queued=True)

    if result.ok:
        op.status = "completed"
        op.operation_code = result.operation_code
        op.response_json = result.to_dict()
        op.completed_at = datetime.now(UTC)
    elif result.http_status == 429:
        # Throttled — leave pending so replay re-issues after backoff.
        op.status = "pending"
        result.queued = True
    else:
        op.status = "failed"
        op.operation_code = result.operation_code
        op.response_json = result.to_dict()
    await session.commit()
    return result


async def replay_pending(
    session: AsyncSession, *, client_id: str, client_secret: str, limit: int = 50
) -> int:
    """Re-issue every ``pending`` intent; return how many reached ``completed``.

    Manual (no background loop): a future worker or ``scripts/hmvs_smoke`` calls
    this. Each replay runs through ``change_state`` directly — the row already
    encodes the guard, so a since-completed pack is simply marked completed.
    """
    pending = (
        await session.scalars(
            select(HmvsOperation).where(HmvsOperation.status == "pending").limit(limit)
        )
    ).all()
    completed = 0
    for op in pending:
        op.attempts = (op.attempts or 0) + 1
        try:
            result = await change_state(
                op.gtin,
                op.serial,
                op.batch,
                op.expiry,
                target_state=op.target_state,
                client_id=client_id,
                client_secret=client_secret,
            )
        except (httpx.TimeoutException, httpx.TransportError):
            continue  # still unreachable — leave pending for the next pass
        if result.ok:
            op.status = "completed"
            op.operation_code = result.operation_code
            op.response_json = result.to_dict()
            op.completed_at = datetime.now(UTC)
            completed += 1
        elif result.http_status != 429:
            op.status = "failed"
            op.operation_code = result.operation_code
            op.response_json = result.to_dict()
    await session.commit()
    return completed


# ── Mock (HMVS_MOCK=true) ────────────────────────────────────────────────────
#
# Canned ITE-style scenarios, selected by sentinel serial values so dev/tests can
# drive every branch without the network:
#   • serial containing "404" → unknown pack (404)
#   • serial containing "409" → already in the requested state (409, current state)
#   • anything else           → genuine active pack / successful supply
_MOCK_NHRN = "GR-0000-0000-0000"


def _mock_verify(serial: str) -> HmvsResult:
    if "404" in serial:
        return HmvsResult(
            ok=False, http_status=404, operation_code="NMVS_NC_PCK_22", raw={"mock": True}
        )
    return HmvsResult(
        ok=True,
        http_status=200,
        operation_code="NMVS_OK",
        state=STATE_ACTIVE,
        nhrn=_MOCK_NHRN,
        is_intermarket=False,
        information="Pack verified (mock).",
        raw={"mock": True},
    )


def _mock_change_state(serial: str, target_state: str) -> HmvsResult:
    if "404" in serial:
        return HmvsResult(
            ok=False, http_status=404, operation_code="NMVS_NC_PCK_22", raw={"mock": True}
        )
    if "409" in serial:
        # Invalid transition — pack already holds the target state.
        return HmvsResult(
            ok=False,
            http_status=409,
            operation_code="NMVS_NC_PCK_19",
            current_state=target_state,
            raw={"mock": True},
        )
    return HmvsResult(
        ok=True,
        http_status=200,
        operation_code="NMVS_OK",
        state=target_state,
        nhrn=_MOCK_NHRN,
        is_intermarket=False,
        raw={"mock": True},
    )
