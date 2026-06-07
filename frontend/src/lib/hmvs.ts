// ── HMVS pack-verification gateway ───────────────────────────────────────────
//
// This module is the ONE AND ONLY place in the frontend permitted to reach the
// upstream HMVS (Hellenic Medicines Verification System) endpoints that the
// backend proxies under `/pharmapi/hmvs/*`. An ESLint `no-restricted-imports`
// rule (see frontend/eslint.config.js) fails the build if any module outside
// the dispense flow imports this file: HMVS is invoked exclusively from the
// dispense action. See docs/hmvs-scope.md for the commitment and the why.
//
// ── Upstream contract (HMVO spec, 3 Jun 2026) ────────────────────────────────
//
// A pack is identified by the GS1 fields decoded from the 2D DataMatrix / QR
// printed on the carton:
//   (01) GTIN    — 14-digit Global Trade Item Number
//   (21) serial  — unique serial number
//   (10) batch   — batch / lot number
//   (17) expiry  — expiry date, YYMMDD
//
//   verify       GET   /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?batch={batch}&expiry={YYMMDD}
//   decommission PATCH (same URL)  body { state: "Supplied" }   ← normal dispense outcome
//   reactivate   PATCH (same URL)  body { state: "Active" }     ← reverses a supply
//
// ── Status ───────────────────────────────────────────────────────────────────
//
// TODO(H6): the backend `/pharmapi/hmvs` proxy is not built yet — it lands in
// Phase 2 and is test-book driven. Until then every entry point fails fast with
// a clear "not yet available" ApiError(501). Signatures and request shapes below
// already match the contract, so wiring at H6 is: decode `qr` → GS1 fields,
// build the URL above, and issue the fetch with `credentials: "include"`
// (mirror the helpers in lib/api.ts) — replacing the body of `hmvsRequest`.

import { ApiError } from "./api";

/** Pack lifecycle states relevant to the dispense flow (EMVS/HMVS subset). */
export type HmvsState = "Active" | "Supplied";

/** Result of a successful pack verification (HMVS GET). */
export interface HmvsVerifyResult {
  /** Current lifecycle state of the pack in the registry. */
  state: HmvsState;
  /** GTIN echoed back by the registry. */
  gtin: string;
  /** Serial echoed back by the registry. */
  serial: string;
}

/** Result of a successful pack state change (HMVS PATCH). */
export interface HmvsStateChangeResult {
  success: boolean;
  /** The state the pack now holds in the registry. */
  state: HmvsState;
}

/** Body of the PATCH that changes a pack's state. */
interface HmvsStateChangeBody {
  state: HmvsState;
  /** Free-text reason, recorded on the audit trail alongside the change. */
  reason?: string;
}

type HmvsOp = "verification" | "decommission" | "reactivation";

/**
 * Single network seam for every HMVS pack operation. Throws until the backend
 * proxy lands (H6); from then on this is the only function that issues the
 * `fetch` to `/pharmapi/hmvs/*`.
 *
 * TODO(H6, Phase 2, test-book driven): replace the guard + throw below with a
 * real request — decode `qr` into its GS1 fields, build
 * `/pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?batch={batch}&expiry={YYMMDD}`,
 * and `fetch` it (GET for verify, PATCH with `body` otherwise) using
 * `credentials: "include"`, routing the response through lib/api.ts's `handle`.
 *
 * `qr` arrives from the dispense wizard in one of two shapes the decoder must
 * handle (see DispenseWizard.tsx handleVerify):
 *   • scan mode   — the raw GS1 DataMatrix payload read off the carton;
 *   • manual mode — a colon-delimited string
 *     `${scheme}:${productCode}:${serial}:${batch}:${expiry}`, scheme "GS1" | "PPN".
 */
function hmvsRequest(op: HmvsOp, qr: string, body?: HmvsStateChangeBody): never {
  if (!qr) {
    throw new ApiError(400, "Missing pack barcode for HMVS operation.");
  }
  const target = body ? ` (target state: ${body.state})` : "";
  throw new ApiError(
    501,
    `HMVS ${op}${target} is not yet available — the /pharmapi/hmvs backend proxy lands in Phase 2 (H6).`,
  );
}

/**
 * Verify a scanned pack against the HMVS registry.
 *
 * Maps to: GET /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?batch={batch}&expiry={YYMMDD}
 *
 * @param qr Raw GS1 DataMatrix / QR payload scanned off the carton.
 * TODO(H6): wire to the backend proxy; currently throws ApiError(501).
 */
export async function hmvsVerify(qr: string): Promise<HmvsVerifyResult> {
  return hmvsRequest("verification", qr);
}

/**
 * Decommission (supply) a scanned pack — the normal dispense outcome.
 *
 * Maps to: PATCH /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?… body { state: "Supplied" }
 *
 * @param qr     Raw GS1 DataMatrix / QR payload scanned off the carton.
 * @param reason Audit reason recorded alongside the upstream state change.
 * TODO(H6): wire to the backend proxy; currently throws ApiError(501).
 */
export async function hmvsDecommission(qr: string, reason: string): Promise<HmvsStateChangeResult> {
  return hmvsRequest("decommission", qr, { state: "Supplied", reason });
}

/**
 * Reactivate a previously-decommissioned pack (reverses a supply within the
 * registry's allowed window).
 *
 * Maps to: PATCH /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?… body { state: "Active" }
 *
 * @param qr Raw GS1 DataMatrix / QR payload scanned off the carton.
 * TODO(H6): wire to the backend proxy; currently throws ApiError(501).
 */
export async function hmvsReactivate(qr: string): Promise<HmvsStateChangeResult> {
  return hmvsRequest("reactivation", qr, { state: "Active" });
}
