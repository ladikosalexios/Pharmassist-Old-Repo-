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
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx
from sqlalchemy import delete, select
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

# EMVS requires an `emvs-data-entry-mode` header on EVERY verify/state-change.
# Omitting it → 422/61020012 ("header required"); an unrecognised value →
# 422/61020013. Crucially the value must reflect HOW the pack identifier was
# captured: sending "manual" for a 2D camera/handheld scan misrepresents the
# dispense. So the mode is threaded from the scanner (camera → 2D, hand-keyed →
# manual) and defaults to the 2D scan value, since the dispense flow is
# scan-driven. ``normalise_data_entry_mode`` coerces untrusted inbound values.
#
# Sandbox note: the Greek IQE currently accepts only "manual" and 422s
# "2d_two_dimensional_barcode"/"2D" (operationCode 61020013). That is a sandbox /
# Solidsoft discrepancy — we send the HONEST value, not whichever one happens to
# pass the sandbox. Confirm the exact accepted 2D token with Solidsoft and update
# EMVS_DATA_ENTRY_2D if it differs.
EMVS_DATA_ENTRY_MANUAL = "manual"
EMVS_DATA_ENTRY_2D = "2d_two_dimensional_barcode"
EMVS_DATA_ENTRY_MODES = frozenset({EMVS_DATA_ENTRY_MANUAL, EMVS_DATA_ENTRY_2D})


def normalise_data_entry_mode(value: str | None) -> str:
    """Coerce an inbound entry-mode to a valid EMVS value.

    Unknown/missing → the 2D scan value (the scan-driven dispense norm), never a
    silent "manual" that would under-report a real scan.
    """
    return value if value in EMVS_DATA_ENTRY_MODES else EMVS_DATA_ENTRY_2D


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
    # Free-text product label echoed by the registry — surfaced in the pack row so
    # a pharmacist can sanity-check what was scanned. None when the upstream omits it.
    product_name: str | None = None
    # Batch-level state (e.g. "Recalled", "Withdrawn"). Populated on 409 conflict
    # responses where the pack itself may be Active but the batch isn't dispensable.
    batch_state: str | None = None
    queued: bool = False
    # Throttle hint from a 429 Retry-After header — seconds the caller should
    # back off before retrying. None for any non-throttled response or when
    # the header was absent / unparseable.
    retry_after_seconds: int | None = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_cached(cls, op: HmvsOperation) -> HmvsResult:
        """Rebuild the result of an already-``completed`` operation from its row."""
        snapshot = op.response_json or {}
        # response_json was written by to_dict(), so it round-trips field-for-field.
        # Filter to known fields so a row written by a NEWER version of the code
        # (extra keys) can still be replayed by an older deploy without raising
        # ``TypeError: unexpected keyword argument``.
        if "ok" in snapshot:
            known = {f.name for f in dataclass_fields(cls)}
            return cls(**{k: v for k, v in snapshot.items() if k in known})
        # Defensive fallback if a row predates the snapshot column.
        return cls(
            ok=True,
            http_status=200,
            operation_code=op.operation_code,
            state=op.target_state,
            raw=snapshot,
        )


def _parse_retry_after(value: str | None) -> int | None:
    """Decode a Retry-After header into seconds-to-back-off.

    RFC 7231 allows two shapes — bare ``delay-seconds`` or an HTTP-date. ITE has
    been observed to use both. Clamps at zero (a date in the past becomes "retry
    now") and returns ``None`` for absent / unparseable values rather than
    raising, so a malformed throttle hint never crashes the dispense path.
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return max(0, int(s))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0, int((dt - datetime.now(UTC)).total_seconds()))


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
        product_name=body.get("productName"),
        batch_state=body.get("batchState"),
        raw=body,
    )

    if r.status_code == 200:
        return HmvsResult(ok=True, http_status=200, state=body.get("state"), **base)
    if r.status_code == 409:
        # Invalid transition — the registry returns the pack's current state.
        return HmvsResult(ok=False, http_status=409, current_state=body.get("state"), **base)
    if r.status_code == 429:
        # Throttled — surface Retry-After so the caller can schedule its backoff.
        return HmvsResult(
            ok=False,
            http_status=429,
            state=body.get("state"),
            retry_after_seconds=_parse_retry_after(r.headers.get("Retry-After")),
            **base,
        )
    # 403 / 404 (incl. batch/expiry mismatch) / 422 / anything else: not ok.
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
    # Evict any expired entries so the cache can't grow unboundedly across
    # distinct client_ids (per-pharmacy IQE creds path).
    for stale in [c for c, v in _token_cache.items() if v["expires_at_ts"] <= now]:
        del _token_cache[stale]
    logger.info("[HMVS] OAuth2 token refreshed (expires in %ss)", expires_in)
    return token


def hmvs_headers(token: str, data_entry_mode: str = EMVS_DATA_ENTRY_2D) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        # Mandatory — see EMVS_DATA_ENTRY_*. Value reflects how the pack was
        # captured (camera/handheld 2D scan vs hand-keyed); without it the IQE
        # 422s every call.
        "emvs-data-entry-mode": data_entry_mode,
    }


# Startup TLS probe target — the NMVO developer portal, which fronts the IDP
# certificate chain we'll need at runtime (the H-cert requirement, R18 of the
# qualification checklist). A handshake failure here is the canonical signal
# that the host trust store doesn't include the NMVO CA, and it surfaces hours
# before the first dispense rather than at the dispense itself.
_TLS_PROBE_URL = "https://developer-ite.nmvo.eu/"


async def probe_developer_tls() -> bool:
    """HEAD the NMVO developer-ite host to confirm the TLS chain validates.

    Returns True on any successful handshake (regardless of HTTP status — 405,
    404 etc. all prove the chain is good). On a handshake failure logs a
    distinct ``[HMVS][TLS]`` error and returns False; never raises, so a
    transient network blip cannot stop the app from booting.
    """
    try:
        async with _client() as client:
            r = await client.head(_TLS_PROBE_URL)
        logger.info("[HMVS][TLS] developer-ite reachable (http=%s)", r.status_code)
        return True
    except (httpx.ConnectError, httpx.ReadError) as exc:
        # httpx wraps the SSL error in ConnectError; the cause carries the
        # underlying ssl.SSLCertVerificationError. Log both so an operator can
        # tell "unknown CA" from "expired cert" from "wrong hostname".
        cause = exc.__cause__ or exc.__context__
        logger.error(
            "[HMVS][TLS] handshake to %s FAILED — %s (cause=%r). "
            "Host trust store likely missing the NMVO CA (R18 H-cert).",
            _TLS_PROBE_URL,
            exc,
            cause,
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning("[HMVS][TLS] probe to %s unreachable: %s", _TLS_PROBE_URL, exc)
        return False


def _pack_url(gtin: str, serial: str) -> str:
    settings = get_settings()
    # GS1 serials carry the full printable character set (e.g. ``AZaz10_/+&"-``);
    # an un-encoded "/" splits the path and the registry 404s. Percent-encode the
    # serial (and gtin, defensively) so every legal pack routes to lookup.
    return (
        f"{settings.hmvs_verification_url}"
        f"/product/gs1/{quote(gtin, safe='')}/pack/{quote(serial, safe='')}"
    )


# ── Verify / state-change ────────────────────────────────────────────────────


async def verify(
    gtin: str,
    serial: str,
    batch: str,
    expiry: str | None,
    *,
    client_id: str,
    client_secret: str,
    data_entry_mode: str = EMVS_DATA_ENTRY_2D,
) -> HmvsResult:
    """GET the pack from the registry to confirm it is genuine/active."""
    if is_mock_hmvs():
        return _mock_verify(serial)
    token = await _get_token(client_id, client_secret)
    async with _client() as client:
        r = await client.get(
            _pack_url(gtin, serial),
            headers=hmvs_headers(token, data_entry_mode),
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
    data_entry_mode: str = EMVS_DATA_ENTRY_2D,
) -> HmvsResult:
    """PATCH the pack to a new state (Supplied on dispense, Active to reverse)."""
    if is_mock_hmvs():
        return _mock_change_state(serial, target_state)
    token = await _get_token(client_id, client_secret)
    async with _client() as client:
        r = await client.patch(
            _pack_url(gtin, serial),
            headers=hmvs_headers(token, data_entry_mode),
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
    data_entry_mode: str = EMVS_DATA_ENTRY_2D,
) -> HmvsResult:
    """``change_state`` wrapped in the double-supply guard + store-and-forward.

    A previously-``completed`` intent short-circuits to its cached result with no
    upstream call. A timeout/transport error or 429 leaves the row ``pending`` for
    ``replay_pending`` and returns a ``queued`` result.

    ``data_entry_mode`` flows to the inline PATCH. NOTE: it is not persisted on
    the intent row, so a later ``replay_pending`` re-issues with the default 2D
    value — acceptable because dispense packs are scanned; persist it (a column)
    if a manual-entry pack's store-and-forward replay must stay byte-honest.
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
        try:
            # Savepoint so a lost insert race rolls back ONLY this row, not any
            # other uncommitted work the request may hold on this session.
            async with session.begin_nested():
                session.add(op)
                await session.flush()
        except IntegrityError:
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
            data_entry_mode=data_entry_mode,
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
        # The pack is now in target_state, so any prior completed intent for a
        # DIFFERENT state on the same pack is stale and must not short-circuit a
        # future change — otherwise supply → reactivate → re-supply would return
        # the first supply's cached result instead of re-hitting the registry.
        await session.execute(
            delete(HmvsOperation).where(
                HmvsOperation.gtin == gtin,
                HmvsOperation.serial == serial,
                HmvsOperation.batch == batch,
                HmvsOperation.target_state != target_state,
                HmvsOperation.status == "completed",
            )
        )
    elif result.http_status == 429:
        # Throttled — leave pending so replay re-issues after backoff. Persist
        # the Retry-After hint so replay_pending can honour the window and the
        # FE can surface "try again in N seconds" instead of a blind retry.
        op.status = "pending"
        op.retry_after_seconds = result.retry_after_seconds
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
            select(HmvsOperation)
            .where(HmvsOperation.status == "pending")
            .order_by(HmvsOperation.created_at)  # oldest-first, deterministic FIFO
            .limit(limit)
        )
    ).all()
    completed = 0
    for idx, op in enumerate(pending):
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
        except httpx.HTTPStatusError as exc:
            # Token endpoint refused the creds (revoked / 401). Every remaining
            # op in this batch shares the same client_id, so spinning through
            # them would hammer the IDP with identical failures. Bail out of the
            # batch and let the next replay_pending pass try again — if the creds
            # have been rotated back by then, the queue drains naturally; if not,
            # one warning per pass beats N. Pending ops stay pending.
            logger.warning(
                "[HMVS] replay halted on auth failure (%s) — %d ops left pending",
                exc,
                len(pending) - idx - 1,
            )
            break
        if result.ok:
            op.status = "completed"
            op.operation_code = result.operation_code
            op.response_json = result.to_dict()
            op.completed_at = datetime.now(UTC)
            completed += 1
        elif result.http_status == 429:
            # Still throttled — refresh the Retry-After hint so the next replay
            # sees the latest window instead of a stale one from the original 429.
            op.retry_after_seconds = result.retry_after_seconds
        else:
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


_MOCK_PRODUCT_NAME = "Mock Pharma Tablet 10mg x28"


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
        product_name=_MOCK_PRODUCT_NAME,
        batch_state=STATE_ACTIVE,
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
            product_name=_MOCK_PRODUCT_NAME,
            raw={"mock": True},
        )
    return HmvsResult(
        ok=True,
        http_status=200,
        operation_code="NMVS_OK",
        state=target_state,
        nhrn=_MOCK_NHRN,
        is_intermarket=False,
        product_name=_MOCK_PRODUCT_NAME,
        batch_state=STATE_ACTIVE,
        raw={"mock": True},
    )
