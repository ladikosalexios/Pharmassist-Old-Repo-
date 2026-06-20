# HMVS scope & containment

**Commitment:** PharmAssist touches the HMVS (Hellenic Medicines Verification
System) **exclusively from the dispense action**. It verifies, decommissions
(supplies) and — where the registry allows — reactivates the specific pack a
pharmacist is handing to a patient, and nothing else. PharmAssist supports **no
inventory, price-check or ordering flows**, and will not grow any: HMVS is not a
stock or commerce backend and we do not treat it as one.

This document records that scope so it survives staff turnover and review, and
explains the guardrail that enforces it in code.

## Why this matters

HMVS / the EU FMD registry is a safety-and-anti-falsification system, not a
catalogue. Querying it for stock levels, pricing, or bulk product data would be
an abuse of its purpose and of the credentials we hold. Keeping the surface tiny
also keeps our regulator-facing audit trail honest: every HMVS call corresponds
to a real dispense event, never to background browsing.

## The single gateway

All HMVS access goes through one file:

- [`frontend/src/lib/hmvs.ts`](../frontend/src/lib/hmvs.ts) — the **only** module
  permitted to call `/pharmapi/hmvs/*` (the backend's proxy to the upstream
  registry).

It exposes exactly three thin operations, all driven by the pack the pharmacist
scans during dispense:

| Function                       | HTTP                              | Purpose                            |
| ------------------------------ | --------------------------------- | ---------------------------------- |
| `hmvsVerify(qr)`               | `GET` the pack URL                | confirm the pack is genuine/active |
| `hmvsDecommission(qr, reason)` | `PATCH` … `{ state: "Supplied" }` | supply the pack on dispense        |
| `hmvsReactivate(qr)`           | `PATCH` … `{ state: "Active" }`   | reverse a supply within the window |

### Upstream contract (HMVO spec, 3 Jun 2026)

A pack is identified by the GS1 fields decoded from the 2D DataMatrix / QR on the
carton — GTIN `(01)`, serial `(21)`, batch `(10)`, expiry `(17)`, `YYMMDD`:

```
verify        GET   /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?batch={batch}&expiry={YYMMDD}
state change  PATCH (same URL)  body { state: "Supplied" | "Active" | … }
```

### Status — built

The integration is **built and exercised against the NMVO ITE / Greek IQE
sandbox** (not yet in production). `frontend/src/lib/hmvs.ts` issues the live
`GET` / `PATCH` calls above against the backend `/pharmapi/hmvs` proxy, and
`backend/app/services/hmvs.py` is a full OAuth2 client-credentials client —
token mint + caching, idempotent state-change (no double-supply on retry), and
store-and-forward replay for transient upstream failures. The three operations
and their request shapes match the contract above.

HMVS calls run live only when `HMVS_MOCK=false`; the flag **defaults to `true`
in dev/CI**, returning canned ITE-style responses with no token fetch. Live
qualification (IQE) runs set `HMVS_MOCK=false` with the registered equipment's
OAuth2 credentials.

## How the boundary is enforced

`frontend/eslint.config.js` carries a `no-restricted-imports` rule that **fails
`npm run lint`** (and therefore CI) if any module imports the HMVS gateway,
with a single override that re-permits the dispense flow:

- Permitted importer: `frontend/src/components/DispenseWizard.tsx` (the dispense
  action).
- Everything else importing `src/lib/hmvs.ts` is a lint error.

If the dispense flow legitimately grows (e.g. split into more files or a
`dispense/` folder), extend the override `files` list in `eslint.config.js` —
deliberately, as a reviewed decision — rather than widening the gateway's reach.

## Out of scope — explicitly

The following are **not** built and are **not** on the roadmap for this bridge:

- inventory / stock-on-hand lookups,
- price checks or reimbursement pricing,
- ordering, wholesaler, or procurement flows.

Any future request for these must be treated as a scope change to be discussed,
not a quiet extension of the HMVS gateway.
