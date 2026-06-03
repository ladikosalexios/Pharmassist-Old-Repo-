# HMVO Compliance & HMVS Integration — Ticket Breakdown

Implementation tickets for the commitments made in the HMVO IT-supplier reply (caps-lock + keyboard-layout safeguards, full Greek UI, NHRN visibility, HMVS verify / decommission / reactivate endpoints, dispense-only scoping, audit trail, test-book delivery).

Companion to `docs/redesign-tickets.md` — both tracks run in parallel. This doc spells out **where they collide**, **how to sequence around it**, and gives each ticket a paste-and-go Claude Code prompt.

## TL;DR

- **17 tickets**, total effort ~**5–6 engineer-weeks**.
- Mostly independent of the redesign, **with 4 explicit coordination points** (see Conflict Matrix below).
- **HMV-6a (i18n foundation) ✅ already landed in PR #98 (FR-0)** — the most critical coordination point is closed before engineering starts.
- **HMV-11 (Dispense wizard HMVS step)** layers on top of FR-3 — FR-3 should ship a non-HMVS dispense flow first; HMV-11 wires HMVS on top once endpoints exist.
- **NEW HMV-16 (R18 Sectigo CA certificates) has a hard deadline of 18 May 2026** — production deployment fails silently against HMVS without it.
- HMVO's test book hasn't arrived yet — HMV-15 is sized as a placeholder; rescope when received.

## Revisions from the HMVO IT-supplier onboarding email (2026-06-02)

This doc was first drafted before the HMVO onboarding details landed. Key corrections from the original draft:

| Original assumption | Reality | Tickets affected |
|---|---|---|
| Endpoints like `POST /api/medicines/lot/qr` | REST on pack URIs: `GET /product/<scheme>/<gtin>/pack/<serial>?batch=...&expiry=...` (verify), `PATCH` same URL with `{"state": "Supplied"}` (state change) | HMV-7, HMV-8, HMV-9 |
| Basic Auth | OAuth 2.0 Client Credentials Grant against `/identity/connect/token` | HMV-2 |
| Credentials per pharmacy | Credentials per **Equipment**. Hierarchy: Organisation → Locations → Equipment. Each Equipment gets its own `client_id` + `client_secret` (cannot be regenerated once lost). | HMV-1 |
| One environment toggle | Three environments: **ITE** (stateless dev sandbox, shared across all Solidsoft markets), **IQE** (Greek-specific qualification, stateful), **PROD** (live) | HMV-13 |
| 4 pack states in `VerifyResponse` enum | 12 states: Active, Supplied, Sample, Destroyed, Stolen, Free Sample, Locked, Exported, Expired, Withdrawn, Recalled, Checked-out | HMV-7 |
| No infrastructure ticket | **New HMV-16: R18 Sectigo CA certificate verification + install** (deadline 18 May 2026) | NEW |
| (not considered) | **`isIntermarket` property** on responses — when pack data lives in another EU country, transaction escalates to EU Hub, slower and returns fewer fields. UI must handle gracefully. | HMV-7, HMV-11 |
| (not considered) | API version `3.1`, datetimes in **UTC** | HMV-2 |
| (not considered) | Public status dashboards (`status-iqe.nmvo.eu`, `status.nmvo.eu`) — link from our error UX | HMV-11 |

## Conflict matrix with the redesign

| HMVO ticket | Redesign ticket(s) it touches | Resolution |
|---|---|---|
| **HMV-1** Credential storage admin UI | **FR-5c** Settings | Coordinate: HMV-1's admin UI form lives inside the Settings screen FR-5c builds. Eng A owns both. |
| **HMV-5** NHRN/EOF display | **FR-2** Review + **FR-3** Dispense | Cross-cutting: NHRN must be present in the prescription detail card (FR-2) and the dispense wizard's drug summary (FR-3). Added as an explicit acceptance criterion in both. |
| **HMV-6a** i18n foundation | **FR-0** Foundation | ✅ Done — landed in PR #98 (FR-0). `react-i18next`, `i18next-browser-languagedetector`, `src/lib/i18n.ts`, `en.json` + `el.json`, Sidebar + AppShell using `t()`. |
| **HMV-11** Dispense wizard HMVS step | **FR-3** Dispense wizard | Layer: FR-3 ships a mock/non-HMVS dispense flow first; HMV-11 layers the HMVS verify / decommission step on top once HMV-7 / HMV-8 / HMV-10 exist. |

The remaining 12 tickets touch backend services or pure-utility frontend components that don't collide with redesign file ownership.

## Engineering allocation

Adding HMVO to the two-engineer redesign team means **carrying it on Eng A** (who owns FR-3 Dispense and FR-5c Settings — the two redesign tickets where HMVO work naturally lives). Eng B stays on the parallel redesign track (FR-2 / FR-4 / FR-5a-b). This adds ~3–4 weeks to Eng A's load on top of the redesign work — so total Eng A timeline goes from ~5d (redesign-only) to ~5d + ~3w (HMVO). Plan accordingly, or add a third engineer.

## Sequencing across both tracks

```
Week 1: [FR-0 ✅ landed via PR #98 including HMV-6a]
        [HMV-1, HMV-2] backend infra (parallel)
        [HMV-3, HMV-4] compliance hooks (parallel)
        [HMV-16] R18 CA cert verification (1 day, parallel — deadline 18 May)

Week 2: [FR-0.5, FR-1, FR-2, FR-4]  ←  redesign work proceeds
        [HMV-7, HMV-8, HMV-9] HMVS endpoints (real REST URLs)
        [HMV-13] three-environment wiring (ITE/IQE/PROD)

Week 3: [FR-3]  ←  base dispense wizard (non-HMVS)
        [HMV-10] data matrix scanner
        [HMV-5] NHRN audit pass

Week 4: [HMV-11] HMVS step layered on FR-3 (with isIntermarket handling)
        [HMV-12] HMVS audit log
        [FR-5a, FR-5b, FR-5c+HMV-1 admin]

Week 5: [HMV-14] screen recording for HMVO
        [HMV-6b] Greek translation pass (now possible because HMV-6a is in)
        [FR-6] polish

Week 6: [HMV-15] test book completion (depends on HMVO sending it)
```

---

# Tickets

## Layer 1 — Backend infrastructure

### HMV-1 — HMVS credential storage (per-Equipment hierarchy)

**Owner:** Eng A
**Branch:** `feat/hmv-1-credential-storage`
**Depends on:** —
**Coordinates with:** FR-5c Settings (admin UI lives there)
**Effort:** 4 days (expanded from 3 — three-level hierarchy is more involved than a single creds row)

#### Scope
HMVS credentials are **per-Equipment**, not per-pharmacy. HMVO's data model is three levels deep:

- **Organisation** — our pharmacy customer (1 per PharmAssist tenant)
- **Locations** — physical pharmacy premises (1+ per organisation; one pharmacy can have multiple licensed premises)
- **Equipment** — individual scanner/POS stations (1+ per location; each has its own OAuth client_id + client_secret)

Each Equipment's `client_id` + `client_secret` is issued **once** at Equipment creation in the HMVO portal and **cannot be regenerated** if lost. Store them encrypted at rest using the existing AES-256-GCM pattern from `app/crypto.py`.

#### Acceptance criteria
- New tables: `hmvs_locations` (FK to pharmacy), `hmvs_equipment` (FK to location, holds encrypted client_id + client_secret + a friendly name like "Scanner 1 - Zebra")
- Alembic migration runs cleanly up + down
- `app/services/hmvs_credentials.py` with three helpers:
  - `get_equipment_credentials(session, equipment_id)` → `(client_id, client_secret) | None`
  - `list_equipment_for_pharmacy(session, pharmacy_id)` → ordered list of `{location, equipment_name, equipment_id}`
  - `register_equipment(session, location_id, name, client_id, client_secret)` → persist with encryption
- Credentials decrypted only in-memory at point of use — never logged, never persisted plaintext
- One Equipment per dispense session at MVP (Settings UI in FR-5c lets the pharmacist pick which Equipment is "active" for this session — multiple-scanner pharmacies pick the right one)
- Unit test for the encrypt-then-decrypt round-trip on `client_secret`

#### Claude Code prompt
```
You are adding HMVS credential storage to PharmAssist. HMVS credentials
follow HMVO's three-level data model: Organisation → Locations → Equipment.
Each Equipment is one scanner/POS station with its own OAuth client_id +
client_secret. Client secrets are issued once and cannot be regenerated.

INPUTS
- Read backend/app/db/models/pharmacist_pharmacy.py — see how
  pharmapi_username + pharmapi_password are encrypted/stored. Pattern to mirror.
- Read backend/app/crypto.py — encrypt_credential / decrypt_credential are
  AES-256-GCM with 12-byte nonce, base64-encoded.
- Read backend/alembic/versions/ for migration style + naming conventions.
- Read backend/app/db/models/pharmacy.py and pharmacist_pharmacy.py to
  understand the relationship pattern (SQLAlchemy 2.0 async, naming
  convention via app/db/base.py MetaData).
- HMVO data model reference (from their onboarding email):
  Organisation (our pharmacy customer)
    └─ Locations (physical premises — auto-generated location code,
       requires HMVO approval after creation)
       └─ Equipment (each scanner/POS gets one client_id + client_secret,
          tracked for forensic audit; CANNOT be regenerated if lost)

STUB CONTRACTS (write these)
# backend/app/db/models/hmvs_location.py
class HmvsLocation(Base, TimestampMixin):
    __tablename__ = "hmvs_locations"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pharmacies.id"))
    hmvo_location_code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None]
    postal_code: Mapped[str | None]
    approved_by_hmvo: Mapped[bool] = mapped_column(Boolean, default=False)
    equipment: Mapped[list["HmvsEquipment"]] = relationship(back_populates="location")

# backend/app/db/models/hmvs_equipment.py
class HmvsEquipment(Base, TimestampMixin):
    __tablename__ = "hmvs_equipment"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hmvs_locations.id"))
    name: Mapped[str] = mapped_column(Text)  # e.g. "Scanner 1 - Zebra"
    client_id_encrypted: Mapped[str] = mapped_column(Text)
    client_secret_encrypted: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    location: Mapped["HmvsLocation"] = relationship(back_populates="equipment")

# backend/app/services/hmvs_credentials.py
async def get_equipment_credentials(
    session: AsyncSession, equipment_id: uuid.UUID,
) -> tuple[str, str] | None: ...

async def list_equipment_for_pharmacy(
    session: AsyncSession, pharmacy_id: uuid.UUID,
) -> list[dict]:
    """Returns [{location_name, location_id, equipment_name, equipment_id}, ...]
    ordered by location name then equipment name."""

async def register_equipment(
    session: AsyncSession, location_id: uuid.UUID,
    name: str, client_id: str, client_secret: str,
) -> uuid.UUID:
    """Encrypt + persist a new Equipment. Returns the equipment_id.
    Caller is responsible for capturing client_id + client_secret from the
    pharmacist immediately after they create the Equipment in the HMVO portal."""

ACCEPTANCE CRITERIA
- Alembic migration creates both tables with proper FKs + indexes.
- Both new model modules imported in alembic/env.py and in app/db/models/__init__.py.
- alembic upgrade head and alembic downgrade -1 both run cleanly.
- backend/app/services/hmvs_credentials.py implements all three functions.
- backend/tests/test_hmvs_credentials.py covers:
  - register_equipment → get_equipment_credentials round-trip
  - list_equipment_for_pharmacy returns correct sort order
  - Encryption uses encrypt_credential; raw client_id/secret are never on the model
- Ruff + ruff format clean.

DO NOT
- Do not log client_id or client_secret anywhere — even at DEBUG.
- Do not store creds on pharmacist_pharmacies (different hierarchy from Pharmapi creds).
- Do not add admin UI endpoints here — that's the FR-5c coordination.
- Do not allow client_secret to be returned over the API — only equipment_id
  references are exposed.

FINALIZE
- Run: cd backend && alembic upgrade head && pytest tests/test_hmvs_credentials.py -v
- Run: cd backend && alembic downgrade -1 && alembic upgrade head
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-1): HMVS Location + Equipment models with encrypted creds"
- PR: "HMV-1: HMVS credential storage (per-Equipment hierarchy)"
```

---

### HMV-2 — HMVS OAuth 2.0 client + token cache

**Owner:** Eng A
**Branch:** `feat/hmv-2-hmvs-client`
**Depends on:** HMV-1
**Effort:** 3 days (expanded from 2 — OAuth flow + token caching adds complexity)

#### Scope
The HMVS HTTP client + OAuth 2.0 Client Credentials flow that all the verify / decommission / reactivate endpoints (HMV-7/8/9) call through. HMVS uses **OAuth 2.0 Client Credentials Grant** — POST to `/identity/connect/token` with `grant_type=client_credentials` + per-Equipment `client_id`/`client_secret`, get back a Bearer token with `expires_in`. Cache the token until expiry.

#### Acceptance criteria
- `app/services/hmvs.py` with `hmvs_get` / `hmvs_patch` taking `(session, equipment_id, path, …)` — token is fetched/cached per Equipment
- OAuth token endpoint, env-configurable per environment (ITE / IQE / PROD)
- Token cache: keyed by `equipment_id`, holds `(access_token, expires_at)`, refreshes 60s before expiry
- API version `3.1` header on every request
- Timestamps in request bodies / response parsing default to **UTC**
- Errors mapped to `HTTPException(502, "HMVS: <code> — <message>")` with HTTP status preserved in a structured way (404/409/422 from HMVS are NOT bugs in our code — they're meaningful upstream states)
- `HMVS_MOCK=true` env toggle short-circuits everything to deterministic stub
- Unit test covers: token fetch + cache hit + cache miss after expiry + 4xx upstream mapping

#### Claude Code prompt
```
You are building the HMVS OAuth 2.0 client. HMVS auth is OAuth 2.0 Client
Credentials Grant — each Equipment (scanner/POS station) has its own
client_id + client_secret, exchanges them for a Bearer token, and uses
that token until it expires.

INPUTS
- Read backend/app/services/pharmapi.py — analogous structure (httpx async,
  singleton client, error mapping), but the auth mechanism is different.
- Read backend/app/services/hmvs_credentials.py (HMV-1) — your credential
  source. Equipment-keyed lookup.
- Read backend/app/config.py — add three URLs: HMVS_BASE_URL_ITE,
  HMVS_BASE_URL_IQE, HMVS_BASE_URL_PROD (defaults: developer-ite.nmvo.eu,
  portal-gr-iqe.nmvo.eu, TBD).
- Read backend/app/utils/environment.py — add is_mock_hmvs() and
  hmvs_environment() (returns 'ite' | 'iqe' | 'prod' from env var
  HMVS_ENV, default 'ite').
- HMVO auth flow (from onboarding email):
  POST /identity/connect/token
  Content-Type: application/x-www-form-urlencoded
  grant_type=client_credentials&client_id=...&client_secret=...
  →
  {"access_token": "eyJ...", "expires_in": 32767, "token_type": "Bearer"}

STUB CONTRACTS
# backend/app/services/hmvs.py
class HmvsToken:
    access_token: str
    expires_at: datetime  # UTC, with 60s safety margin

# Module-level cache: { equipment_id: HmvsToken }
_token_cache: dict[uuid.UUID, HmvsToken] = {}

async def get_or_refresh_token(
    session: AsyncSession, equipment_id: uuid.UUID,
) -> str:
    """Return a valid Bearer token for this Equipment, fetching or refreshing
    from /identity/connect/token if cached token is missing or near expiry.
    Uses client credentials from get_equipment_credentials (HMV-1)."""

async def hmvs_get(
    session: AsyncSession, equipment_id: uuid.UUID, path: str,
    *, params: dict | None = None,
) -> tuple[int, dict]:
    """GET with Bearer auth. Returns (http_status, parsed_json).
    Status NOT mapped to exception here — caller interprets 404/409/422
    as meaningful HMVS responses, not bugs."""

async def hmvs_patch(
    session: AsyncSession, equipment_id: uuid.UUID, path: str,
    *, json: dict,
) -> tuple[int, dict]:
    """PATCH with Bearer auth. Used for state changes (Supplied, Active, etc.)."""

# backend/app/utils/environment.py — add:
def is_mock_hmvs() -> bool: ...
def hmvs_environment() -> Literal['ite', 'iqe', 'prod']: ...

ACCEPTANCE CRITERIA
- All requests carry headers: Authorization: Bearer <token>, Accept:
  application/json, X-NMVS-API-Version: 3.1.
- Token cache: stores access_token + expires_at (UTC, with 60s margin
  before actual expiry). On expired or missing entry, re-fetch via
  get_or_refresh_token. Concurrent callers must not double-fetch — use
  an asyncio.Lock per equipment_id.
- When is_mock_hmvs() returns True, every call returns deterministic stubs
  without touching network. Mock responses configurable via a module-level
  dict for test scenarios (e.g. HMVS_MOCK_RESPONSES[(equipment_id, 'GET',
  '/product/...')] = (200, {...})).
- Base URL chosen via hmvs_environment() → maps to ITE/IQE/PROD URLs from
  config.
- backend/tests/test_hmvs_client.py covers:
  - Token fetch on first call, cache hit on second
  - Token refresh after expires_at - 60s
  - 200 OK PATCH returns (200, body)
  - 404 from upstream returns (404, body) — NOT an exception
  - Network error raises HTTPException(502, "HMVS: network error — ...")
  - Mock mode returns configured stub
  - Concurrent calls for same equipment_id only fetch token once (lock test)

DO NOT
- Do not retry automatically — HMVS PATCH state-changes are non-idempotent
  (decommission means decommission). Caller decides retry.
- Do not log access_token, client_id, or client_secret.
- Do not log request bodies — they contain pack serials.
- Do not raise on 404/409/422 — caller needs the status to interpret pack state.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_client.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-2): HMVS OAuth 2.0 client with per-Equipment token cache"
- PR: "HMV-2: HMVS client (OAuth Client Credentials, depends on HMV-1)"
```

---

## Layer 2 — Compliance safeguards (HMVO requirements)

### HMV-3 — Caps Lock blocker hook + input component

**Owner:** Eng A (or Eng B — pure frontend utility)
**Branch:** `feat/hmv-3-caps-lock-blocker`
**Depends on:** —
**Effort:** 1 day

#### Scope
HMVO requires that any input field that will feed an HMVS submission must block the submission while Caps Lock is on, and show a Greek warning. We build this as a reusable hook + an `<HmvsSecureInput>` component so every place we accept a pack serial number gets the same protection.

#### Acceptance criteria
- `frontend/src/hooks/useCapsLockState.ts` returns the current Caps Lock state (boolean), updates on keyboard events while the bound input is focused
- `frontend/src/components/HmvsSecureInput.tsx` is the input component to use for HMVS serial / GTIN fields:
  - Renders an `<input>` with the i18n string for the field label
  - When Caps Lock is on, sets `aria-invalid`, disables the submit button via context, shows a Greek warning ("Απενεργοποιήστε το Caps Lock πριν συνεχίσετε")
  - Emits an `onBlock(reason)` callback so the parent form's submit handler can react
- Unit test (Vitest) covers: Caps Lock off → no block, Caps Lock on → block + warning, Caps Lock toggled off → block clears

#### Claude Code prompt
```
You are building a reusable input component for HMVS data entry that blocks
submission while Caps Lock is active. HMVO requires this because case-sensitive
HMVS serial numbers typed with Caps Lock generate false counterfeit alerts.

INPUTS
- Read frontend/src/components for the existing component style (Tailwind,
  no styled-components, no CSS modules). Use the patterns you find.
- Read frontend/src/lib/i18n.ts (or wherever HMV-6a placed the i18n setup —
  if it's not there yet, this ticket is blocked. Stop and tell the user.)
- Web platform reference: KeyboardEvent.getModifierState('CapsLock') is the
  detection method. Bind to keydown and keyup on the input.

STUB CONTRACT
// frontend/src/hooks/useCapsLockState.ts
export function useCapsLockState(ref: RefObject<HTMLInputElement>): boolean;

// frontend/src/components/HmvsSecureInput.tsx
interface HmvsSecureInputProps {
  value: string;
  onChange: (v: string) => void;
  onBlock?: (reason: 'caps-lock' | null) => void;
  label: string;            // already-translated string
  warningText?: string;     // defaults to i18n('hmvs.capsLockWarning')
  placeholder?: string;
}
export function HmvsSecureInput(props: HmvsSecureInputProps): JSX.Element;

ACCEPTANCE CRITERIA
- useCapsLockState returns true the moment Caps Lock is detected as active
  on any key event from the bound input; returns false otherwise.
- HmvsSecureInput renders:
  - The input itself with the given value/onChange
  - When Caps Lock active: aria-invalid="true", a warning element with
    role="alert" containing the Greek warning string, a red border via
    Tailwind (border-red-500), and onBlock('caps-lock') is called.
  - When Caps Lock not active: warning hidden, onBlock(null) called once
    on transition.
- Greek string: "Απενεργοποιήστε το Caps Lock πριν συνεχίσετε" — pulled
  from i18n if HMV-6a is in place; hardcoded as fallback with a TODO if not.
- Vitest test in HmvsSecureInput.test.tsx asserts:
  - Initial render: no warning, onBlock not called with caps-lock
  - Fire keydown with getModifierState mocked to return true for CapsLock:
    warning appears, onBlock('caps-lock') called
  - Fire keydown with caps lock false: warning disappears, onBlock(null) called

DO NOT
- Do not poll for Caps Lock state — only react to keyboard events on the
  bound input. Polling battery-drains and triggers false positives.
- Do not block the input from receiving characters — only block the
  submission. The user might be typing to investigate before submitting.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Commit: "feat(hmv-3): Caps Lock blocker hook and HmvsSecureInput component"
- Open PR: "HMV-3: Caps Lock submission blocker (HMVO compliance)"
```

---

### HMV-4 — Keyboard layout blocker hook + input augmentation

**Owner:** Eng A
**Branch:** `feat/hmv-4-keyboard-layout-blocker`
**Depends on:** HMV-3 (extends the same `HmvsSecureInput`)
**Effort:** 3–4 days

#### Scope
HMVO requires blocking HMVS submissions while the OS keyboard layout is not English. Browsers don't expose the OS keyboard layout directly; the workaround is to analyse typed input — if a Greek (or other non-Latin) character lands in the HMVS field, the layout is wrong, block and warn.

#### Acceptance criteria
- `frontend/src/hooks/useNonLatinInputDetector.ts` watches input value, detects presence of non-Latin characters using a regex (`/[^\x00-\x7F]/`)
- `<HmvsSecureInput>` extended to also block on non-Latin input: warning text in Greek ("Αλλάξτε τη γλώσσα πληκτρολογίου σε αγγλικά πριν συνεχίσετε"), `onBlock('keyboard-layout')` callback
- Both block conditions can be active simultaneously — both warnings shown, submission blocked until both cleared
- The screen-recording deliverable (HMV-14) will exercise this exact component

#### Claude Code prompt
```
You are extending HmvsSecureInput from HMV-3 to also block HMVS submissions
when a non-Latin keyboard layout is detected. Browsers can't read the OS
layout directly — we detect by analysing characters typed into the input.

INPUTS
- Read the HmvsSecureInput component built in HMV-3 (frontend/src/components/
  HmvsSecureInput.tsx). Extend it; do not create a new component.
- Read the i18n setup (assume HMV-6a has landed — if not, stop and tell the
  user this ticket is blocked).
- The detection regex /[^\x00-\x7F]/ matches any non-ASCII character. This
  is the cleanest signal that the user has typed a Greek (or otherwise
  non-Latin) character. Latin extended characters (ñ, é) would also flag —
  acceptable false positive for our domain (HMVS serial numbers are ASCII).

STUB CONTRACT
// frontend/src/hooks/useNonLatinInputDetector.ts
export function useNonLatinInputDetector(value: string): boolean;

// HmvsSecureInput onBlock callback now emits a union:
type BlockReason = 'caps-lock' | 'keyboard-layout' | 'both' | null;

ACCEPTANCE CRITERIA
- useNonLatinInputDetector(value) returns true if value contains any
  non-ASCII character, false otherwise. Memoised on value.
- HmvsSecureInput now blocks on EITHER caps-lock OR non-Latin input:
  - Both blockers show their respective warning, stacked
  - onBlock receives 'caps-lock', 'keyboard-layout', 'both', or null
  - Submission disabled when any blocker active
- Greek warning string: "Αλλάξτε τη γλώσσα πληκτρολογίου σε αγγλικά πριν
  συνεχίσετε" — pulled from i18n.
- Extended Vitest tests:
  - Input "ABC" (Latin): no keyboard-layout block
  - Input "ΑΒΓ" (Greek): keyboard-layout block fires, warning shown
  - Caps Lock + Greek input: both warnings shown, onBlock('both')
  - Clear the Greek chars: keyboard-layout block clears

DO NOT
- Do not try to detect via navigator.keyboard.getLayoutMap() — browser
  support is poor and HMVO's standard is OS-level. Document in a code
  comment that browser-native detection is unavailable.
- Do not block ALL inputs from receiving non-Latin chars — only HMVS
  submission. The patient name field, for example, must accept Greek.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Commit: "feat(hmv-4): non-Latin keyboard layout blocker on HmvsSecureInput"
- Open PR: "HMV-4: Keyboard layout submission blocker (HMVO compliance)"
```

---

### HMV-5 — NHRN/EOF code visibility audit (cross-cutting)

**Owner:** Eng B (works on FR-2 / FR-4 — natural overlap)
**Branch:** Folded into FR-2 + FR-3 PRs as acceptance criteria
**Depends on:** —
**Effort:** 1–2 days

#### Scope
HMVO requires that the NHRN (κωδικός ΕΟΦ — the Greek drug ID) is visible to the end user wherever a medicine is shown in a verification or dispense flow. This isn't a standalone PR; it's an acceptance criterion that gets added to FR-2 (Review screen) and FR-3 (Dispense wizard) and verified before each merges.

#### Acceptance criteria for FR-2 / FR-3 reviews to apply
- The prescription detail view (FR-2) displays the NHRN/EOF code alongside the drug name
- The dispense wizard's drug summary step (FR-3) displays the NHRN/EOF code
- The code is labelled `Κωδικός ΕΟΦ` (Greek) in the production UI
- The data source: `medicineBarcode` from the v2 search result IS the NHRN — no new endpoint needed
- Visible at glance without hover/expand

#### Claude Code prompt
```
This is a coordination item, not a standalone implementation. The NHRN
(κωδικός ΕΟΦ — Greek drug ID) must be visible to the pharmacist in the
prescription review screen (FR-2) and the dispense wizard's drug summary
step (FR-3). HMVO requires this for compliance.

INPUTS
- The NHRN value is already available in our v2 search response as
  `medicineBarcode`. Read backend/app/services/pharmapi.py
  _parse_prescription_search_json to confirm.
- The label "Κωδικός ΕΟΦ" should come from i18n (HMV-6a).

ACCEPTANCE CRITERIA
- In the FR-2 PR review, verify:
  - The prescription detail card shows the NHRN labelled "Κωδικός ΕΟΦ"
  - Visible at glance, not behind hover or expand
- In the FR-3 PR review, verify the same for the drug summary step of the
  dispense wizard
- If either FR-2 or FR-3 ships without this, block the merge and request
  the addition. This is an HMVO compliance item, not a nice-to-have.

DO NOT
- Do not open a separate PR for this. The work is two CSS / JSX additions
  inside FR-2 and FR-3.

FINALIZE
- After FR-2 and FR-3 both merge with NHRN visible, mark HMV-5 done.
- No standalone commit needed.
```

---

### HMV-6a — i18n foundation ✅ DELIVERED

**Status:** ✅ **Done — landed in PR #98 (FR-0)**
**Owner:** cosmic-explore (Nick) on the redesign track
**Effort actual:** ~1 day (bundled with FR-0)

#### What landed

PR #98 delivered the full i18n foundation as part of FR-0:

- `react-i18next` `^17.0.8`, `i18next` `^26.3.0`, `i18next-browser-languagedetector` `^8.2.1` installed
- `frontend/src/lib/i18n.ts` — i18next initialised with Greek as default, detection order: `querystring → localStorage → navigator`, localStorage key `pharmassist_lang`, `initImmediate: false` for sync init
- `frontend/src/locales/en.json` + `frontend/src/locales/el.json` — both populated with the initial key set (nav, common, etc.)
- `frontend/src/main.tsx` — imports `./lib/i18n` before `<App />` mounts
- `frontend/src/components/AppShell.tsx` — loading string + keyboard shortcut toast already using `t()`
- `frontend/src/components/Sidebar.tsx` — all 5 nav items using `t('nav.*')`

#### Convention for subsequent FR-N work

Every redesign ticket from FR-0.5 onwards **must** use `t('...')` for any visible string. No hardcoded English in JSX. The `check-i18n.sh` heuristic from HMV-6b will catch violations during the polish pass.

#### Coordination follow-up

- Update `docs/redesign-tickets.md` (a one-line note in the top section) to make the t() convention explicit for downstream FR engineers — without it, components written before FR-6b lands will leak English strings into the codebase and we'll have a bigger HMV-6b cleanup.

---

### HMV-6b — Full Greek translation pass

**Owner:** Eng A (during FR-6 polish)
**Branch:** `feat/hmv-6b-greek-translation`
**Depends on:** HMV-6a, all FR-N tickets landed
**Effort:** 1.5–2 weeks

#### Scope
Sweep every component in the redesign, find all visible strings, externalise into `t('...')` calls if not already, and provide Greek translations in `el.json`. Includes form labels, button text, error messages, modal copy, table headers, empty states, validation messages, dates/numbers (use Intl APIs).

#### Acceptance criteria
- 100% of visible strings in the redesigned UI use `t('...')` — verified by a script that greps for hardcoded English (heuristic: any string in JSX containing 3+ ASCII alpha chars not wrapped in `t()`)
- `el.json` has Greek translations for every key
- `en.json` retained as the source-of-truth for the key inventory
- A native Greek speaker (the user, or a contractor) reviews and signs off on the translation quality before merge — clinical terminology is sensitive
- Pre-built terminology mapping in the PR description (Serial Number → Σειριακός Αριθμός, Batch → Παρτίδα, Pack → Συσκευασία, NHRN → Κωδικός ΕΟΦ, etc.)

#### Claude Code prompt
```
You are doing the full Greek translation pass for the PharmAssist frontend.
HMVO requires that the entire UI is in Greek — every visible string,
including button labels, validation errors, table headers, empty states,
and modal copy. The i18n plumbing is already in place from HMV-6a.

INPUTS
- Read frontend/src/lib/i18n.ts and frontend/src/locales/{en,el}.json —
  these exist and have an example key.
- Read every component under frontend/src/components/ and
  frontend/src/pages/ — these all need string externalisation.
- Reference glossary (use these consistently across the translation):
  Serial Number → Σειριακός Αριθμός
  Batch → Παρτίδα
  Pack → Συσκευασία
  NHRN / EOF code → Κωδικός ΕΟΦ
  Prescription → Συνταγή
  Patient → Ασθενής
  Medicine / Drug → Φάρμακο
  Pharmacist → Φαρμακοποιός
  Dispense → Διάθεση / Δοσοληψία (context-dependent — see below)
  Verify → Επαλήθευση
  Decommission → Απενεργοποίηση
  Reactivate → Επανενεργοποίηση
  Safety check → Έλεγχος ασφάλειας
  Side effect / ADR → Παρενέργεια / Ανεπιθύμητη Ενέργεια
  AMKA → ΑΜΚΑ (no translation, just transliteration)
  ΗΔΥΚΑ → ΗΔΥΚΑ (no change)
  Dosage → Δοσολογία
  Quantity → Ποσότητα
- "Dispense" is the dispense ACTION when used as a verb; "διάθεση"
  is the noun for the result. Read context, pick the right one.

WORK PLAN
1. Sweep every .tsx file under frontend/src/. For every visible string
   (any string rendered in JSX), externalise to t('key').
2. Use hierarchical keys: components.SafetyAlertsPanel.title,
   pages.Counter.scanCta, common.cancel, errors.networkFailure, etc.
3. Add the English original to en.json and the Greek translation to el.json.
4. For pluralisation, use react-i18next's count interpolation:
   t('items.count', { count: items.length })
5. For dates, use Intl.DateTimeFormat with locale 'el-GR' when current
   language is 'el'.

ACCEPTANCE CRITERIA
- A grep heuristic (provide a script in tools/check-i18n.sh) returns zero
  hardcoded English strings in JSX. The heuristic looks for: JSX text
  content matching /[A-Z][a-z]{3,}/ that isn't inside a t() call.
- el.json has 100% coverage of keys in en.json.
- The user (or a native Greek speaker they nominate) reviews and approves
  the translations before merge — flag this in the PR description as a
  required review.
- The app loads in Greek by default; ?lang=en still works.
- npm run typecheck, lint, build all pass.

DO NOT
- Do not auto-translate clinical terminology with Google Translate without
  human review. Pharmacy terms are sensitive — wrong word = wrong care.
- Do not invent Greek translations for HMVS or ΗΔΥΚΑ terms — they are used
  as-is in Greek pharmacy software.
- Do not change the i18n setup itself — extend the locale files only.

FINALIZE
- Run: cd frontend && bash tools/check-i18n.sh && npm run typecheck &&
  npm run lint && npm run build
- Commit: "feat(hmv-6b): full Greek translation pass for redesigned UI"
- PR description: include the terminology glossary used, and request
  native-speaker review explicitly.
```

---

## Layer 3 — HMVS endpoint integration

### HMV-7 — Verify endpoint (GET on pack URI)

**Owner:** Eng A
**Branch:** `feat/hmv-7-verify-endpoint`
**Depends on:** HMV-2
**Effort:** 2-3 days

#### Scope
The verify endpoint — proxies a GET to HMVS to check whether a pack is genuine, in date, not already dispensed. **The real HMVS URL pattern is REST on a pack URI**, not a POST:

```
GET /product/<scheme>/<productCode>/pack/<serialNumber>?batch=<batch>&expiry=<expiry>
e.g. GET /product/gs1/05060141900022/pack/96392630670?batch=DemoPack&expiry=210300
```

Returns pack state (12 possible states) + product info + `nhrn` + `isIntermarket` flag.

#### Acceptance criteria
- `POST /pharmapi/hmvs/verify` accepts `{equipment_id: UUID, pack: ScannedPack}` body — Equipment must be active for the current pharmacy
- Endpoint **parses the scanned GS1/IFA payload first** (don't pass raw QR to HMVS — extract GTIN/serial/batch/expiry, build the pack URI)
- Calls `hmvs_get` (HMV-2) with the constructed URI
- Returns the **12-state** pack status + `nhrn` + `isIntermarket` flag + decoded pack details
- HTTP statuses preserved with meaning:
  - 200 → pack found, state in response body
  - 404 → pack not found in repository (includes batch/expiry mismatch — a verification *signal*, not an error)
  - 409 → state conflict (rare on GET — still report cleanly)
  - 422 → malformed pack URI (our bug — log and 500 to the SPA)
  - 429 → throttled (surface to user as "try again shortly")
- `isIntermarket: true` responses must NOT block the caller — degraded data is acceptable, surface a UI note
- Audit log (HMV-12 TODO) records the verify outcome
- Tests cover: 200 with each pack state, 404 not-found, 422 malformed, intermarket response, mock-mode stub

#### Claude Code prompt
```
You are building the HMVS verify endpoint. The real HMVS API is REST on
pack URIs (not POST to a verification endpoint). Each scanned pack QR is
parsed locally to extract GTIN + serial + batch + expiry, then we GET the
pack URI.

INPUTS
- Read backend/app/services/hmvs.py (HMV-2) — hmvs_get returns (status, body).
- Read frontend/src/lib/gs1.ts (HMV-10) — the GS1/IFA payload parser.
- Read backend/app/routers/pharmapi.py — proxy router style.
- HMVS verify contract (from HMVO email):
  GET /product/<scheme>/<productCode>/pack/<serialNumber>?batch=<batchId>&expiry=<expiry>
  - <scheme>: 'gs1' or 'ifa'
  - <productCode>: GTIN-14 (for GS1) or PPN (for IFA)
  - <serialNumber>: 1-20 chars from GS1 Character Set 82
  - <batch>: 1-20 chars
  - <expiry>: YYMMDD
- HMVS response (200 OK) shape:
  {
    "operationCode": 11210000,  # use to determine UI presentation/colour
    "state": "Active" | "Supplied" | "Sample" | "Destroyed" | "Stolen"
           | "Free Sample" | "Locked" | "Exported" | "Expired"
           | "Withdrawn" | "Recalled" | "Checked-out",
    "information": "...",   # optional friendly text
    "warning": "...",       # optional warning text
    "nhrn": "...",          # κωδικός ΕΟΦ
    "isIntermarket": false  # true if pack data was fetched from another EU market
  }
- HTTP statuses:
  200 OK = pack found
  404 = pack not in repo (or batch/expiry mismatch) — meaningful signal, NOT a bug
  409 = state conflict (rare on GET)
  422 = malformed request (our bug)
  429 = throttled

STUB CONTRACTS
# backend/app/routers/hmvs.py (new file or extend if HMV-2 created it)
router = APIRouter(prefix="/pharmapi/hmvs", tags=["hmvs"])

PackState = Literal[
    "Active", "Supplied", "Sample", "Destroyed", "Stolen",
    "Free Sample", "Locked", "Exported", "Expired",
    "Withdrawn", "Recalled", "Checked-out",
]

class ScannedPack(BaseModel):
    scheme: Literal["gs1", "ifa"]
    product_code: str   # GTIN or PPN
    serial: str
    batch: str
    expiry: str         # YYMMDD as HMVS expects

class VerifyRequest(BaseModel):
    equipment_id: uuid.UUID
    pack: ScannedPack

class VerifyResponse(BaseModel):
    found: bool                       # False if HMVS returned 404
    state: PackState | None
    operation_code: int | None
    nhrn: str | None
    is_intermarket: bool
    information: str | None
    warning: str | None
    http_status: int                  # for the SPA to render appropriate UX
    upstream_message: str | None      # parsed from response body if non-200

@router.post("/verify", response_model=VerifyResponse)
async def hmvs_verify(
    body: VerifyRequest,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> VerifyResponse:
    ...

ACCEPTANCE CRITERIA
- Router added to main.py app.include_router list.
- Endpoint validates equipment_id belongs to current user's pharmacy
  (via HMV-1 list_equipment_for_pharmacy). 403 if not.
- URL construction: f"/product/{scheme}/{product_code}/pack/{serial}?batch={batch}&expiry={expiry}"
  - URL-encode all path/query segments
- hmvs_get returns (http_status, body). Map to VerifyResponse:
  - 200 → found=True, state=body["state"], operation_code=body["operationCode"],
    nhrn=body.get("nhrn"), is_intermarket=body.get("isIntermarket", False),
    information, warning, http_status=200
  - 404 → found=False, state=None, http_status=404, upstream_message="Pack not
    found or batch/expiry mismatch"
  - 422 → log error + raise HTTPException(500, "Internal pack URI error") —
    this is our bug, never the user's
  - 429 → raise HTTPException(429, "HMVS throttling — try again shortly")
  - Other → raise HTTPException(502, f"HMVS: {http_status}")
- Audit log: leave TODO comment for HMV-12.
- backend/tests/test_hmvs_verify.py covers:
  - 200 Active state mapped correctly
  - 200 Supplied state (already-dispensed pack)
  - 200 Recalled state
  - 200 with isIntermarket=true returns the flag through
  - 404 returns found=False without raising
  - 422 raises 500 (logged)
  - HMVS_MOCK=true returns deterministic Active stub
  - Equipment not owned by current user → 403

DO NOT
- Do not raise an exception on 404 — it's a valid HMVS response state.
- Do not log raw QR or serial numbers — privacy.
- Do not handle decommission/state-change here — that's HMV-8 (PATCH).
- Do not retry on failure.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_verify.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-7): POST /pharmapi/hmvs/verify (GET pack URI proxy)"
- PR: "HMV-7: HMVS pack verify (real REST URL pattern, depends on HMV-2)"
```

---

### HMV-8 — Decommission endpoint (PATCH state change)

**Owner:** Eng A
**Branch:** `feat/hmv-8-decommission-endpoint`
**Depends on:** HMV-2, HMV-7 (same router file)
**Effort:** 2 days

#### Scope
`POST /pharmapi/hmvs/decommission` — called the moment a pack is dispensed. **Real HMVS pattern is PATCH on the pack URI with `{"state": "<target>"}` body.** Target state ∈ Supplied / Destroyed / Sample / Stolen / Free Sample / Locked. For normal dispense, target is `Supplied`.

State change is non-idempotent (decommission removes the pack from the live registry) — must NOT be called twice for the same pack. Local idempotency log enforces this.

#### Acceptance criteria
- `POST /pharmapi/hmvs/decommission` accepts `{equipment_id, pack, target_state}` body (target_state defaults to `"Supplied"`)
- Builds the same pack URI as HMV-7
- Calls `hmvs_patch` with `json={"state": target_state}`
- 200 = state change accepted (also covers "already in requested state" — treated as idempotent success)
- 409 = upstream rejected the state change (e.g. pack already in incompatible state) → surface to caller
- Local `hmvs_decommission_log` table with unique `(pharmacy_id, serial)` constraint — 5-minute idempotency cache
- Audit log entry (HMV-12 TODO)

#### Claude Code prompt
```
You are building the HMVS decommission endpoint. This is a STATE-CHANGING
call to HMVS that must not be made twice for the same pack. Real pattern is
PATCH on the pack URI with {"state": "Supplied"} body — NOT a POST to a
dedicated decommission endpoint.

INPUTS
- Read backend/app/routers/hmvs.py (HMV-7) — extend it; do not create a new file.
- Read backend/app/services/hmvs.py (HMV-2) — hmvs_patch is your transport.
- HMVS state-change contract (from HMVO email):
  PATCH /product/<scheme>/<productCode>/pack/<serialNumber>?batch=...&expiry=...
  Body: {"state": "Supplied"}
  Response (200): same shape as verify (operationCode, state, [warning], nhrn)
  Response (409): system rejected state change; body has current state + reason
  Idempotency: "if the pack is already in the requested state, the request is
  treated as valid" — so 200 covers both "just changed" and "was already there"

STUB CONTRACT
class DecommissionTarget(str, Enum):
    SUPPLIED = "Supplied"
    DESTROYED = "Destroyed"
    SAMPLE = "Sample"
    STOLEN = "Stolen"
    FREE_SAMPLE = "Free Sample"
    LOCKED = "Locked"

class DecommissionRequest(BaseModel):
    equipment_id: uuid.UUID
    pack: ScannedPack            # reuse from HMV-7
    target_state: DecommissionTarget = DecommissionTarget.SUPPLIED

class DecommissionResponse(BaseModel):
    success: bool
    final_state: PackState | None
    operation_code: int | None
    upstream_message: str | None
    decommissioned_at: datetime | None  # UTC
    idempotent_cached: bool = False     # True if we returned a cached response

@router.post("/decommission", response_model=DecommissionResponse)
async def hmvs_decommission(...): ...

ACCEPTANCE CRITERIA
- New Alembic migration: hmvs_decommission_log table with columns:
  id (PK uuid), pharmacy_id (FK), serial (text indexed), gtin (text),
  target_state (text), upstream_response (JSONB), decommissioned_at
  (timestamptz default now() UTC). Unique constraint on (pharmacy_id, serial).
- Endpoint logic:
  1. Validate equipment ownership (same as HMV-7).
  2. Parse pack (already done — comes in as ScannedPack).
  3. Idempotency check: SELECT from hmvs_decommission_log where
     (pharmacy_id, serial) match AND decommissioned_at within last 5 min.
     If hit, return cached response with idempotent_cached=true.
  4. Otherwise call hmvs_patch with {"state": body.target_state.value}.
  5. On 200: INSERT into hmvs_decommission_log, return DecommissionResponse(
     success=True, final_state=body["state"], operation_code, decommissioned_at=
     datetime.now(UTC), upstream_message=body.get("information")).
  6. On 409: return DecommissionResponse(success=False, final_state=body["state"]
     if present, upstream_message=body.get("information") or "State change rejected").
     DO NOT insert into the log.
  7. On 404: return DecommissionResponse(success=False, upstream_message="Pack
     not found — cannot decommission"). DO NOT insert into log.
  8. On other status: raise HTTPException(502, ...).
- backend/tests/test_hmvs_decommission.py covers:
  - Happy path: success=True, log row written
  - Same pack within 5 min: idempotent_cached=True, upstream NOT called
  - 409 from upstream: success=False, no log row, surfaced cleanly
  - 404 from upstream: success=False, no log row
  - HMVS_MOCK=true returns success stub

DO NOT
- Do not retry on failure — could double-dispense if first call succeeded
  but response was lost.
- Do not allow hard deletes from hmvs_decommission_log — append-only.
- Do not log QR or serial.
- Do not assume PATCH is idempotent at the HTTP level — use the local table.

FINALIZE
- Run: cd backend && alembic upgrade head && pytest tests/test_hmvs_decommission.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-8): POST /pharmapi/hmvs/decommission (PATCH pack URI)"
- PR: "HMV-8: HMVS decommission (PATCH state, depends on HMV-7)"
```

---

### HMV-9 — Reactivate endpoint (PATCH back to Active)

**Owner:** Eng A
**Branch:** `feat/hmv-9-reactivate-endpoint`
**Depends on:** HMV-2, HMV-8 (extends same router)
**Effort:** 1 day

#### Scope
`POST /pharmapi/hmvs/reactivate` — undo a decommission within HMVO's ~10-day reactivation window. **Real pattern is PATCH on the pack URI with `{"state": "Active"}`.** On success, clears the local idempotency entry so the pack can be re-dispensed cleanly later.

#### Acceptance criteria
- `POST /pharmapi/hmvs/reactivate` accepts `{equipment_id, pack}` body
- Calls `hmvs_patch` with `{"state": "Active"}`
- 200 → success, DELETE from `hmvs_decommission_log` for `(pharmacy_id, serial)`
- 409 → most common failure (outside reactivation window), return `upstream_message` so UI can show the pharmacist why
- Audit log entry (HMV-12 TODO)

#### Claude Code prompt
```
You are building the HMVS reactivate endpoint — the "undo" for HMV-8.
Real pattern is PATCH on the pack URI with {"state": "Active"} body. HMVS
allows reactivation within ~10 days; after that, packs are permanently
retired and PATCH→Active returns 409.

INPUTS
- Read backend/app/routers/hmvs.py (HMV-7 + HMV-8). Extend; do not create new.
- HMVS reactivate contract:
  PATCH /product/<scheme>/<productCode>/pack/<serial>?batch=...&expiry=...
  Body: {"state": "Active"}
  Common failure: 409 with body.information explaining (e.g. "outside
  reactivation window").

STUB CONTRACT
class ReactivateRequest(BaseModel):
    equipment_id: uuid.UUID
    pack: ScannedPack

class ReactivateResponse(BaseModel):
    success: bool
    final_state: PackState | None
    upstream_message: str | None

@router.post("/reactivate", response_model=ReactivateResponse)
async def hmvs_reactivate(...): ...

ACCEPTANCE CRITERIA
- Validates equipment ownership.
- Calls hmvs_patch with {"state": "Active"}.
- On 200: DELETE FROM hmvs_decommission_log WHERE pharmacy_id=... AND
  serial=... (so a fresh decommission can happen cleanly to a different
  patient).
- On 409: return success=False, upstream_message=body.get("information") or
  "Reactivation rejected (likely outside window)". Log row stays intact.
- On 404: success=False, upstream_message="Pack not found".
- backend/tests/test_hmvs_reactivate.py covers:
  - Happy path: success=True, log row deleted
  - 409 outside window: success=False, log row intact, informative message
  - HMVS_MOCK=true returns success stub
  - Validates equipment ownership

DO NOT
- Do not retry — reactivation failures are usually permanent (out of window).
- Do not allow reactivate without a prior decommission log row in mock mode
  (sanity check).

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_reactivate.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-9): POST /pharmapi/hmvs/reactivate (PATCH to Active)"
- PR: "HMV-9: HMVS reactivate (undo for HMV-8)"
```

---

### HMV-10 — 2D Data Matrix pack scanner component

**Owner:** Eng A or Eng B (pure frontend component)
**Branch:** `feat/hmv-10-data-matrix-scanner`
**Depends on:** —
**Effort:** 3–5 days

#### Scope
A reusable React component that uses the device camera to scan a 2D Data Matrix barcode (the format used on EU prescription drug packs under FMD). Decodes the GS1 payload to extract GTIN + serial + batch + expiry, displays a confirmation, emits `onScan(payload)`. Falls back to a manual entry field (with `HmvsSecureInput`) if camera unavailable.

#### Acceptance criteria
- `frontend/src/components/DataMatrixScanner.tsx` component
- Uses `@zxing/browser` or `quagga2` for scanning (validate library size, pick smallest viable)
- On successful scan: parse the GS1 payload (`(01)GTIN(21)serial(17)expiry(10)batch`), emit `onScan({gtin, serial, expiry, batch})`
- Camera permission UX: clear ask, fallback to manual entry if denied
- Manual entry mode uses `HmvsSecureInput` (HMV-3 + HMV-4) so Caps Lock + keyboard layout blockers still apply
- Mobile-responsive: works on tablet (iPad) — that's the likely deployment form-factor
- Vitest test for the GS1 parser

#### Claude Code prompt
```
You are building a 2D Data Matrix scanner component for EU FMD pharmacy packs.
This is what the pharmacist uses to verify a pack against HMVS before
dispensing. Format is GS1-encoded Data Matrix (DIFFERENT from the prescription
barcode — that one is 1D and 16 digits).

INPUTS
- Read frontend/src/components/HmvsSecureInput.tsx (HMV-3 + HMV-4) — the
  manual entry fallback uses this so Caps Lock + keyboard layout blockers
  apply.
- Library choice: @zxing/browser (~120kb gzipped, actively maintained,
  supports Data Matrix). Install:
  cd frontend && npm install @zxing/browser
- GS1 application identifiers in the payload:
  (01) GTIN — 14 digits
  (21) Serial — variable, ASCII
  (17) Expiry — YYMMDD (6 digits)
  (10) Batch — variable, ASCII
  GS1 uses ASCII 29 (FNC1, group separator) between variable-length fields.

STUB CONTRACT
// frontend/src/components/DataMatrixScanner.tsx
interface ScannedPack {
  gtin: string;
  serial: string;
  expiry: string;  // YYYY-MM-DD (converted from YYMMDD)
  batch: string;
  rawPayload: string;
}

interface DataMatrixScannerProps {
  onScan: (pack: ScannedPack) => void;
  onError?: (error: string) => void;
  allowManualEntry?: boolean;  // default true
}

export function DataMatrixScanner(props: DataMatrixScannerProps): JSX.Element;

// frontend/src/lib/gs1.ts
export function parseGs1Payload(raw: string): ScannedPack | null;

ACCEPTANCE CRITERIA
- DataMatrixScanner renders a <video> element with @zxing/browser bound to it.
- Asks for camera permission via getUserMedia. On denial, shows the manual
  entry fallback (HmvsSecureInput for each field).
- On successful scan: parse payload with parseGs1Payload, emit onScan.
- On scan error (unreadable, not a GS1 Data Matrix): emit onError.
- Works on iPad (validate the camera selection — prefer environment-facing).
- frontend/src/lib/gs1.test.ts covers:
  - Standard payload with all four AIs (01, 21, 17, 10)
  - Payload with FNC1 separators between variable fields
  - Malformed payload returns null
  - Expiry "260931" (invalid date) returns null
- Component test: camera permission denial → manual entry mode visible.

DO NOT
- Do not store the camera feed anywhere (no recording, no upload).
- Do not auto-submit after a single scan — show a confirmation step where
  the pharmacist sees the decoded values and confirms.
- Do not use a library that pulls in a >500kb wasm blob — the iPad
  deployment may have spotty connectivity.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Manual smoke: open the scanner on iPad, scan a real pack (or printed
  test Data Matrix), verify decoded fields match.
- Commit: "feat(hmv-10): 2D Data Matrix scanner with manual entry fallback"
- PR: "HMV-10: Pack scanner component (FMD compliance)"
```

---

### HMV-11 — Dispense wizard HMVS step (layers onto FR-3)

**Owner:** Eng A
**Branch:** `feat/hmv-11-dispense-wizard-hmvs`
**Depends on:** FR-3, HMV-7, HMV-8, HMV-10
**Effort:** 3–5 days

#### Scope
The actual user-visible HMVS integration: add a "verify each pack" step to the dispense wizard built in FR-3. For each medicine on the prescription, the pharmacist scans the pack with HMV-10, the app verifies via HMV-7, and on dispense confirm decommissions via HMV-8.

#### Acceptance criteria
- FR-3 dispense wizard gains a new step between drug summary and dispense confirm: **"Verify packs"**
- For each medicine: scanner widget (HMV-10), shows verification result (HMV-7 response), blocks progression if any pack returns DECOMMISSIONED / EXPIRED / RECALLED
- On dispense confirm: each verified pack is decommissioned (HMV-8) sequentially; UI shows progress
- If any decommission fails partway: pharmacist sees clearly which packs were decommissioned and which weren't, with reactivate (HMV-9) option for completed ones
- All copy in Greek
- E2E manual test: scan two real test packs, verify, decommission, observe HMVS state via sandbox console

#### Claude Code prompt
```
You are wiring HMVS verification into the dispense wizard (FR-3). This is
where the pharmacist's actual day-to-day FMD compliance happens — for every
prescription dispensed, every pack must be verified against HMVS before
dispense and decommissioned at dispense confirm.

INPUTS
- Read frontend/src/pages/Dispense/* (whatever FR-3 named the dispense
  wizard). Identify the step before "confirm dispense".
- Read frontend/src/components/DataMatrixScanner.tsx (HMV-10) — your scan UI.
- Read frontend/src/lib/api.ts — add hmvsVerify(qrCode) and
  hmvsDecommission(qrCode, reason) wrappers that call /pharmapi/hmvs/verify
  and /pharmapi/hmvs/decommission.

STUB CONTRACT
// frontend/src/pages/Dispense/steps/VerifyPacksStep.tsx
interface VerifyPacksStepProps {
  medicines: Array<{ nhrn: string; commercialName: string; quantity: number }>;
  onAllVerified: (verifiedPacks: VerifiedPack[]) => void;
  onCancel: () => void;
}

interface VerifiedPack {
  medicineNhrn: string;
  scannedPack: ScannedPack;  // from HMV-10
  verifyStatus: 'VERIFIED' | 'DECOMMISSIONED' | 'EXPIRED' | 'RECALLED' | 'UNKNOWN';
}

// frontend/src/pages/Dispense/steps/ConfirmDispenseStep.tsx
// (modify the existing FR-3 confirm step)
// On confirm: for each verified pack, call hmvsDecommission. Show
// per-pack progress. If any fail, show retry/reactivate options.

ACCEPTANCE CRITERIA
- A new VerifyPacksStep added between FR-3's drug-summary and confirm-dispense
  steps. Mounted in the wizard's step machine.
- For each medicine, render a scanner instance (HMV-10). Pharmacist can scan
  multiple packs if quantity > 1.
- Each scan triggers hmvsVerify; result displayed inline as
  ✅ Verified / ❌ Decommissioned / ❌ Expired / ❌ Recalled.
- Progression to confirm-dispense step is BLOCKED until:
  - Number of verified packs per medicine matches quantity prescribed
  - All packs have status VERIFIED (any other status blocks)
- Confirm step: on click, calls hmvsDecommission for each verified pack
  sequentially. Shows progress bar + per-pack status.
- Partial-failure UX: clearly show which packs were decommissioned and
  which weren't. For decommissioned packs, offer a "Reactivate" button
  that calls hmvsReactivate (the user might want to abort the dispense
  if a later pack fails).
- All copy via t() — strings include:
  steps.VerifyPacks.title: "Επαλήθευση Συσκευασιών"
  steps.VerifyPacks.scanPrompt: "Σκανάρετε τη συσκευασία"
  steps.VerifyPacks.verifyOk: "Επαληθεύτηκε"
  steps.VerifyPacks.verifyFailed: "Αποτυχία επαλήθευσης"
  steps.ConfirmDispense.decommissionProgress: "Απενεργοποίηση συσκευασιών..."
  steps.ConfirmDispense.partialFailure: "Μερική αποτυχία — δείτε λεπτομέρειες"

DO NOT
- Do not parallelise decommission calls. Sequential is safer — partial
  failure is recoverable; concurrent partial failure is much harder to
  reason about.
- Do not auto-reactivate on failure. Pharmacist decides.
- Do not allow the wizard to advance past the verify step if any pack is
  in a non-VERIFIED state, even if the pharmacist tries to "skip" it.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Manual smoke (when sandbox creds available): full flow through a 2-medicine
  prescription with 1 pack each. Verify pre-dispense, dispense, see HMVS
  state shows decommissioned in the HMVO sandbox console.
- Commit: "feat(hmv-11): HMVS verify + decommission steps in dispense wizard"
- PR: "HMV-11: Dispense wizard HMVS integration (depends on FR-3, HMV-7/8/10)"
```

---

## Layer 4 — Validation & delivery

### HMV-12 — HMVS audit log

**Owner:** Eng A
**Branch:** `feat/hmv-12-hmvs-audit`
**Depends on:** HMV-7, HMV-8, HMV-9 (extends them with audit calls)
**Effort:** 1 day

#### Scope
Use the existing `app/services/audit.py` (PR #76) pattern to append an `AuditLog` row for every HMVS verify, decommission, and reactivate call. Closes the TODOs left in those endpoints.

#### Acceptance criteria
- Each of HMV-7 / HMV-8 / HMV-9 endpoints fire `log_documentation_action` (or a new `log_hmvs_action`) on every call
- Audit action strings: `HMVS_VERIFY`, `HMVS_DECOMMISSION`, `HMVS_REACTIVATE`
- Resource type: `HMVS_PACK`, resource_id: the pack's serial number
- Fire-and-forget pattern (same as PR #76) — never blocks the user-facing response
- Failures logged at WARNING, never raised
- Shutdown drain handler added if not already (per my PR #76 review)

#### Claude Code prompt
```
You are extending the existing audit log infrastructure (PR #76) to cover
HMVS operations. Every verify, decommission, and reactivate call must
write an immutable audit row.

INPUTS
- Read backend/app/services/audit.py — log_documentation_action is the
  pattern. Either reuse it with a generic action string, or add a sibling
  log_hmvs_action that takes the same shape. Prefer the latter for clarity.
- Read backend/app/routers/hmvs.py (HMV-7, HMV-8, HMV-9). Each has a TODO
  comment for the audit call — replace those.

STUB CONTRACT
# backend/app/services/audit.py — add:
async def log_hmvs_action(
    *,
    pharmacist_id: uuid.UUID | None,
    pharmacy_id: uuid.UUID | None,
    action: Literal["HMVS_VERIFY", "HMVS_DECOMMISSION", "HMVS_REACTIVATE"],
    serial: str | None = None,
    outcome: str | None = None,  # "success" | "failure" | upstream code
) -> None:
    """Fire-and-forget audit row for HMVS operations. Never blocks the
    request. Failures log at WARNING."""

ACCEPTANCE CRITERIA
- log_hmvs_action implemented in audit.py using the same independent-session +
  background-task pattern as log_documentation_action.
- Each of HMV-7 / HMV-8 / HMV-9 endpoint handlers calls fire_audit_task(
  log_hmvs_action(...)) (or the equivalent module-level set tracking pattern
  from PR #76).
- AuditLog rows:
  - action ∈ {HMVS_VERIFY, HMVS_DECOMMISSION, HMVS_REACTIVATE}
  - resource_type = "HMVS_PACK"
  - resource_id = pack serial (NOT the full QR code — privacy)
- Shutdown drain handler exists in main.py for _background_tasks. If it
  doesn't exist yet (i.e., PR #76's follow-up never landed), add it:

  # main.py
  from app.services.audit import _background_tasks
  @app.on_event("shutdown")
  async def _drain_audit_tasks():
      if _background_tasks:
          await asyncio.gather(*_background_tasks, return_exceptions=True)

- Tests: extend test_hmvs_verify / decommission / reactivate to assert that
  an audit row was written after the response.

DO NOT
- Do not write the full QR code as the resource_id — just the serial.
- Do not store the upstream response body in the audit row — only the outcome.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_*.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-12): audit log entries for HMVS operations"
- PR: "HMV-12: HMVS audit trail (closes TODOs in HMV-7/8/9)"
```

---

### HMV-13 — Three-environment wiring (ITE / IQE / PROD)

**Owner:** Eng A
**Branch:** `feat/hmv-13-three-environments`
**Depends on:** HMV-1, HMV-2
**Effort:** 1-2 days

#### Scope
HMVS has **three distinct environments** with different URLs, purposes, and statefulness — wire all three into our config so engineers can target the right one for each phase of work. Plus public status dashboards for outage signalling.

| Env | Purpose | URL | Stateful | Cred isolation |
|---|---|---|---|---|
| **ITE** | Dev — canned response lookup, all Solidsoft markets share | `developer-ite.nmvo.eu` | No | Shared across all markets |
| **IQE** | Greek-specific qualification / test book | `portal-gr-iqe.nmvo.eu` | Yes, dedicated Greek instance | Per-Equipment creds from IQE portal |
| **PROD** | Live | (TBD post-qualification) | Yes | Per-Equipment creds from PROD portal |

#### Acceptance criteria
- `backend/.env.example` updated with all three `HMVS_BASE_URL_*` + `HMVS_ENV` toggle + `HMVS_MOCK`
- `backend/.env.hmvs.example` template with placeholders + comments on where credentials come from
- `scripts/hmvs_smoke.py` argparse takes `--env {ite,iqe,prod}` + `--equipment-id` + `--test-pack`, exits 0 on success
- `docs/hmvs-setup.md` covers: getting access to each env, registering equipment in each portal, capturing client_id/secret, env-switching, status dashboards
- Status dashboard URLs documented for outage signalling in UI:
  - IQE: `https://status-iqe.nmvo.eu`
  - PROD: `https://status.nmvo.eu`

#### Claude Code prompt
```
You are wiring all three HMVS environments (ITE/IQE/PROD) into our config
and writing the developer setup docs. HMVS has shared dev (ITE), Greek-
specific qualification (IQE), and production environments — each needs
its own URL, credentials, and switching mechanism.

INPUTS
- Read backend/.env.example — pattern for new env vars.
- Read backend/app/config.py — extend with three HMVS_BASE_URL_* + HMVS_ENV.
- Read backend/app/services/hmvs.py (HMV-2) — uses hmvs_environment() to
  pick the right URL.
- Read backend/scripts/seed.py — script style (argparse, asyncio.run).

DELIVERABLES
1. backend/.env.example — add:
   # HMVS environment toggle: 'ite' (default), 'iqe', or 'prod'
   HMVS_ENV=ite
   HMVS_BASE_URL_ITE=https://developer-ite.nmvo.eu
   HMVS_BASE_URL_IQE=https://portal-gr-iqe.nmvo.eu
   HMVS_BASE_URL_PROD=  # filled in post-qualification
   HMVS_MOCK=true

2. backend/.env.hmvs.example — template:
   # Copy to .env.hmvs and override for your dev needs.
   # Equipment credentials are NOT here — they live in the DB (HMV-1)
   # via the Settings admin UI after registration in the HMVO portal.
   #
   # For ITE: any Solidsoft market shares the same canned-response sandbox.
   #          Get developer portal access via hmvo.support@reply.com.
   # For IQE: Greek-specific, requires Equipment registration in the IQE
   #          portal at portal-gr-iqe.nmvo.eu. Receive Client ID + Secret
   #          on Equipment creation — save them immediately, cannot be
   #          regenerated.
   # For PROD: granted only after IQE testbook passes qualification.
   HMVS_ENV=ite
   HMVS_MOCK=false

3. backend/scripts/hmvs_smoke.py:
   import argparse, asyncio
   parser.add_argument("--env", choices=["ite", "iqe", "prod"], default="ite")
   parser.add_argument("--equipment-id", required=True, help="UUID from
       HMVS Equipment registered via HMV-1")
   parser.add_argument("--test-pack", action="store_true",
       help="Use the hardcoded HMVO sample pack instead of --gtin/--serial/etc")
   parser.add_argument("--gtin"); parser.add_argument("--serial");
   parser.add_argument("--batch"); parser.add_argument("--expiry")

   async def main():
       os.environ["HMVS_ENV"] = args.env
       from app.services.hmvs import hmvs_get  # late import after env set
       async with AsyncSessionLocal() as session:
           pack_uri = f"/product/gs1/{gtin}/pack/{serial}?batch={batch}&expiry={expiry}"
           status, body = await hmvs_get(session, args.equipment_id, pack_uri)
           print(f"Status: {status}")
           print(json.dumps(body, indent=2))
           sys.exit(0 if status == 200 else 1)

4. docs/hmvs-setup.md — covers ALL of:
   # HMVS Developer Setup
   ## Environments
   <table of ITE/IQE/PROD>
   ## Getting access
   - ITE: email hmvo.support@reply.com with HMVO in CC. Name, email,
     company. ~few days.
   - IQE: gated on completing the test book in HMVO's onboarding portal.
   - PROD: gated on passing qualification.
   ## Registering Equipment
   - Log into the env-specific portal (ITE: developer-ite.nmvo.eu, IQE:
     portal-gr-iqe.nmvo.eu, PROD: TBD).
   - Locations → Add Location (requires HMVO approval after creation).
   - Equipment → Create Equipment (name + type, e.g. "Scanner 1 - Zebra").
   - **Save the Client ID + Secret immediately** — they cannot be regenerated.
   - Pass them to PharmAssist via the Settings admin UI (HMV-1).
   ## Smoke test
   $ cd backend
   $ HMVS_MOCK=true python scripts/hmvs_smoke.py --env ite --equipment-id <uuid> --test-pack
   ## Switching environments
   $ HMVS_ENV=iqe python -m uvicorn main:app --reload
   ## Status dashboards
   - IQE: https://status-iqe.nmvo.eu
   - PROD: https://status.nmvo.eu
   These are pinged from our error UI when HMVS calls fail — pharmacist
   can check before contacting support.
   ## Going to production checklist
   - [ ] Real Equipment IDs registered in PROD portal
   - [ ] HMVS_ENV=prod, HMVS_MOCK=false
   - [ ] HMVS_BASE_URL_PROD filled in
   - [ ] Equipment credentials set in Settings admin UI
   - [ ] R18 Sectigo CA certs verified on prod server (HMV-16)
   - [ ] Screen recording (HMV-14) sent to HMVO
   - [ ] Test book passed (HMV-15)

ACCEPTANCE CRITERIA
- All four files in place.
- HMVS_MOCK=true smoke runs without any real HMVO access and prints a
  mock response — useful for engineers without sandbox creds.
- docs/hmvs-setup.md is comprehensive enough that a new engineer can
  bootstrap without asking the team.

DO NOT
- Do not commit real Client IDs or Secrets to the repo, ever — even in
  .env.example.
- Do not write a script that mutates state (no decommission in smoke).
- Do not assume PROD URL — leave blank until HMVO provides it post-qualification.

FINALIZE
- Run: cd backend && HMVS_MOCK=true python scripts/hmvs_smoke.py
  --env ite --equipment-id <any-uuid> --test-pack
- Commit: "feat(hmv-13): three-environment wiring (ITE/IQE/PROD) + setup docs"
- PR: "HMV-13: Three HMVS environments + smoke script + setup docs"
```

---

### HMV-14 — Screen recording deliverable for HMVO

**Owner:** Eng A (or designate)
**Branch:** N/A — deliverable lives outside the repo
**Depends on:** HMV-3, HMV-4 deployed to a runnable environment
**Effort:** 0.5 day

#### Scope
Record a screen capture showing the Caps Lock blocker (HMV-3) and the keyboard layout blocker (HMV-4) firing correctly when a pharmacist attempts to submit HMVS data with Caps Lock on / Greek keyboard active. Send the recording to HMVO via email per their pre-qualification requirement.

#### Acceptance criteria
- Recording shows:
  - Caps Lock turned on → attempted submission → Greek warning shown, submission blocked
  - Caps Lock turned off → submission proceeds
  - Greek keyboard active → typed Greek chars in the field → warning shown, submission blocked
  - English keyboard restored → submission proceeds
- Recording is ≤2 minutes, captioned in Greek
- Sent to the HMVO contact from the original email thread, referencing the IT-suppliers ticket number
- A copy is archived in `docs/hmvo-deliverables/screen-recording-2026-XX.mp4` (or linked in `docs/hmvo-deliverables/README.md` if git-lfs unavailable)

#### Claude Code prompt
```
This is a delivery item — record a screen capture proving HMV-3 (Caps Lock
blocker) and HMV-4 (keyboard layout blocker) work as committed in the HMVO
reply, and send it to HMVO via email.

INPUTS
- Branch with HMV-3 + HMV-4 deployed, running locally or on a staging URL
  the recorder can access.
- Reference the original HMVO email thread (the one in the IT-suppliers
  inbox you're CC'd on).

RECORDING SCRIPT
1. Open the app in a fresh browser session.
2. Navigate to a screen with an HMVS data entry field (e.g. the dispense
   wizard's pack verification step, or a dedicated demo page).
3. Type a sample HMVS serial number with Caps Lock OFF — show the field
   accepts input normally.
4. Turn Caps Lock ON — show the warning message appearing in Greek, the
   submit button disabling.
5. Turn Caps Lock OFF — show the warning clearing, submit re-enabling.
6. Switch keyboard layout to Greek (Cmd+Space on Mac, Alt+Shift on Windows).
7. Type a character — show the Greek character lands in the field, the
   warning message appears in Greek, submit disabled.
8. Switch back to English layout, clear the field — show warning clears,
   submit re-enabled.
9. End recording.

ACCEPTANCE CRITERIA
- Recording is ≤2 minutes (ideally 60-90 seconds).
- Both warnings clearly visible in Greek.
- File format: .mp4 or .mov, H.264 codec for broad compatibility.
- File size <50MB (compress if needed).
- Email to HMVO contact (from the original email thread) with:
  - Subject: "PharmAssist — Screen recording: Caps Lock & keyboard layout
    safeguards (IT supplier ticket #...)"
  - Body: brief Greek note confirming this delivers on points 5 + 6 of the
    pre-qualification requirements
  - Recording attached or linked (Google Drive / WeTransfer if too large)
- Archive in docs/hmvo-deliverables/ (create dir if needed). If the file is
  >10MB and git-lfs isn't set up, store the file elsewhere and add the link
  to docs/hmvo-deliverables/README.md.

DO NOT
- Do not record showing patient data or real prescriptions — use mock data
  only.
- Do not record any other features beyond what the script covers — focus.

FINALIZE
- Send the email.
- Add docs/hmvo-deliverables/README.md noting the recording was sent,
  with date, recipient, and link/checksum.
- Commit: "docs(hmv-14): HMVO screen recording delivery log"
```

---

### HMV-15 — Test book completion

**Owner:** Eng A + Eng B (whichever has bandwidth at that phase)
**Branch:** `feat/hmv-15-test-book`
**Depends on:** HMV-13 (sandbox access) + HMVO sending the test book
**Effort:** 3–7 days (rescope when test book arrives)

#### Scope
The HMVO test book is a structured checklist of scenarios our software must execute successfully against their sandbox to qualify for production access. Until they send it, we don't know exactly what's in scope. This ticket is a placeholder; reshape into concrete sub-tickets once the test book lands.

#### Acceptance criteria (template)
- Test book received from HMVO
- Each test scenario documented in `docs/hmvo-deliverables/test-book-results.md` with: scenario number, description, our execution log, pass/fail, screenshots/recordings
- All required scenarios pass
- Results submitted to HMVO via the IT-suppliers portal
- Production HMVS access granted

#### Claude Code prompt
```
This ticket is a placeholder pending receipt of the HMVO test book. When
the test book arrives, scope individual sub-tickets per scenario and link
them here.

EXPECTED CONTENT (typical IT-supplier test books):
- Verify scenarios: valid pack, decommissioned pack, expired pack, recalled
  pack, unknown serial
- Decommission scenarios: happy path, idempotency, partial-batch
- Reactivate scenarios: within window, outside window
- Negative scenarios: Caps Lock blocker, keyboard layout blocker
- Error scenarios: HMVS unreachable, malformed response

PLACEHOLDER WORK NOW (before test book arrives)
- Create docs/hmvo-deliverables/test-book-results.md with section headers
  for likely scenarios and a "TODO: rescope when test book arrives" note
  at the top.
- Verify all the prerequisites are in place (HMV-1 through HMV-14 all
  merged) before HMVO is told we're ready to take the test book.

WHEN TEST BOOK ARRIVES
- Read it end-to-end before writing any code or sub-tickets.
- Open one PR per scenario group (not one giant PR — easier to review and
  retry if any fail).
- Each PR includes: code changes (if any), test scenario execution log,
  screenshots / recordings as evidence.

DO NOT
- Do not start the test book until HMV-1 through HMV-14 are all merged.
- Do not assume scenario specifics — wait for the document.

FINALIZE (when complete)
- Submit results bundle to HMVO via the IT-suppliers portal.
- Wait for HMVO sign-off.
- Commit: "feat(hmv-15): HMVO test book completion + sign-off"
```

---

### HMV-16 — R18 Sectigo CA certificate verification (HARD DEADLINE: 18 May 2026)

**Owner:** Eng A or DevOps
**Branch:** `feat/hmv-16-r18-ca-certs`
**Depends on:** —
**Effort:** 1 day (potentially less if Linux base image already has the certs)
**🚨 Hard deadline:** 18 May 2026 — after this date, HMVS production calls fail silently against any server lacking the new CAs.

#### Scope

HMVS upgrades to R18 on **18 May 2026**, switching SSL Certificate Authority from the old chain to **Sectigo Public Server Authentication Root R46** + sub-CA **Sectigo Public Server Authentication CA DV R36**. After R18 PROD deployment:

- Servers WITHOUT the new CAs will receive an SSL cert validation error on every NMVS call
- HMVS will appear to be down (no response) when it's actually up
- Failures will be silent — no error code, just connection failure

Fully-patched Windows / Azure environments ship with these CAs. **Linux containers (our backend) may NOT** — depends on the base image and how recently it was rebuilt.

#### Acceptance criteria

- Smoke-check from each environment (dev container, staging container, production container) that `curl https://developer-ite.nmvo.eu/` returns HTTP 200, NOT an SSL error
- If missing, install both CA certs in the container's trust store
- Add the CA cert installation to the Dockerfile (or base image) so future rebuilds inherit them
- Document the check + fix procedure in `docs/hmvs-setup.md` (HMV-13's doc)
- Add a startup check that logs a clear warning if the CAs are missing (defence-in-depth)
- Verified by 1 May 2026 at the latest (2-week buffer before HMVO PROD deadline)

#### Claude Code prompt

```
You are verifying and (if necessary) installing the Sectigo R18 root + sub
CA certificates on our backend container. HMVS upgrades to R18 on 18 May
2026 — without these CAs, every NMVS call from our server will fail SSL
validation silently. Fully-patched Linux + Java environments may not have
them; Windows + Azure usually do.

INPUTS
- Read backend/Dockerfile — base image (likely python:3.13-slim or similar)
  may or may not include the Sectigo R46 + R36 CAs.
- Read docs/hmvs-setup.md (HMV-13) — extend with the CA verification section.
- Cert references (publicly available):
  - Root CA: Sectigo Public Server Authentication Root R46
    https://crt.sh/?d=4256644734
  - Sub CA: Sectigo Public Server Authentication CA DV R36
    https://crt.sh/?d=4267304690
- HMVO verification method (from their email): visit
  https://developer-ite.nmvo.eu/ from the target machine — if loads,
  CAs are present; if SSL error, CAs are missing.

WORK
1. From the backend container (docker compose exec backend bash):
   curl -I https://developer-ite.nmvo.eu/
   - 200 = good, skip installation
   - SSL cert error = continue to step 2

2. Install both CAs. On Debian/Ubuntu base:
   # Download the CAs to /usr/local/share/ca-certificates/ as .crt files
   wget -O /usr/local/share/ca-certificates/sectigo-root-r46.crt \
       https://crt.sh/?d=4256644734
   wget -O /usr/local/share/ca-certificates/sectigo-sub-r36.crt \
       https://crt.sh/?d=4267304690
   update-ca-certificates
   # Re-verify: curl -I https://developer-ite.nmvo.eu/  → expect 200

3. Bake the install into backend/Dockerfile so future rebuilds inherit:
   # After base image, before dependency install:
   COPY infra/sectigo-root-r46.crt /usr/local/share/ca-certificates/
   COPY infra/sectigo-sub-r36.crt /usr/local/share/ca-certificates/
   RUN update-ca-certificates
   # Commit the .crt files to infra/ so build is reproducible (these are
   # public certs, safe to commit).

4. Add a startup check to main.py (lifespan startup event):
   async def _verify_hmvs_ca_certs():
       try:
           async with httpx.AsyncClient(timeout=5) as client:
               r = await client.get("https://developer-ite.nmvo.eu/")
               if r.status_code != 200:
                   logger.warning(
                       "HMVS CA check: developer-ite.nmvo.eu returned %s — "
                       "verify Sectigo R46+R36 CAs are installed.",
                       r.status_code,
                   )
       except ssl.SSLError as e:
           logger.error(
               "HMVS CA check: SSL validation FAILED — Sectigo R46+R36 "
               "CAs are likely missing. NMVS calls will fail after R18 "
               "deployment on 2026-05-18. See docs/hmvs-setup.md.",
               exc_info=True,
           )
       except Exception:
           # Network unreachable etc — don't block startup
           pass
   # Register in the lifespan startup event but don't block (asyncio.create_task)

5. Update docs/hmvs-setup.md with a new section "R18 CA certificate
   requirement" — include:
   - The 18 May 2026 deadline
   - The two cert names and crt.sh links
   - The curl check
   - The Dockerfile install pattern
   - The startup-check warning

ACCEPTANCE CRITERIA
- `curl -I https://developer-ite.nmvo.eu/` from the running backend
  container returns 200.
- backend/Dockerfile installs both certs and runs update-ca-certificates.
- infra/sectigo-root-r46.crt and infra/sectigo-sub-r36.crt committed.
- Startup check in main.py logs WARNING on missing CAs without blocking
  app startup.
- docs/hmvs-setup.md has the R18 section.
- Verified working in dev container by 1 May 2026.
- Verified working in production container by 10 May 2026 (1 week before
  HMVO deadline).

DO NOT
- Do not skip the Dockerfile install step — if it only lives in the
  running container, the next rebuild loses it.
- Do not block app startup on the CA check — a transient network issue
  during boot shouldn't prevent the app from running.
- Do not commit any private keys — only the public CA certs (which are
  public knowledge anyway).

FINALIZE
- Run: docker compose build backend && docker compose up -d
- Run: docker compose exec backend curl -I https://developer-ite.nmvo.eu/
  (expect HTTP/2 200)
- Commit: "feat(hmv-16): install Sectigo R46+R36 CAs for HMVS R18 release"
- PR: "HMV-16: R18 Sectigo CA certificates (hard deadline 2026-05-18)"
```

---

## Coordination notes

- **Daily rebase** for branches that touch shared files (HMV-7 / 8 / 9 / 12 all touch `routers/hmvs.py`)
- **Cross-track review**: redesign engineer reviews HMVO PRs touching frontend (HMV-3 / 4 / 10 / 11); HMVO engineer reviews redesign PRs touching FR-3 / FR-5c
- **HMVO contact protocol**: any clarification needed from HMVO goes through the user (single point of contact), not directly from engineers
- **Sandbox access timeline**: every ticket from HMV-7 onward CAN be developed in mock mode (`HMVS_MOCK=true`) but needs sandbox validation before HMV-15. Plan sandbox-access milestone before HMV-15 starts.

## Out of scope

- Production HMVS (only sandbox until HMV-15 passes)
- Multi-pharmacy HMVS credential management (single pharmacy per session in scope; chain customers come later)
- HMVS rate-limiting / quota tracking (assume HMVO sandbox doesn't enforce)
- Customer-facing pricing for HMVS feature (handled in B2B pricing doc separately)
