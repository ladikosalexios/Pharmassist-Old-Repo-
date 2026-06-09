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
// The backend proxy normalises every upstream response (200 / 409 / 429 / …)
// into the structured body declared by `HmvsPackResponse`. A 409 conflict
// (recalled / withdrawn / expired / already-supplied) returns a populated body
// — the FE reads it as data, NOT as an error. Only transport / auth / 5xx
// without a parseable body raises ApiError.

import { ApiError } from "./api";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

/** Pack lifecycle states relevant to the dispense flow (EMVS/HMVS subset). */
export type HmvsState = "Active" | "Supplied";

/** GS1 fields scanned off the carton — the input to every HMVS call. */
export interface HmvsPackKey {
  /** GS1 (01) — 14-digit Global Trade Item Number. */
  gtin: string;
  /** GS1 (21) — unique pack serial. */
  serial: string;
  /** GS1 (10) — batch / lot. */
  batch: string;
  /** GS1 (17) — expiry, YYMMDD. */
  expiry: string;
}

/**
 * Normalised response from the backend HMVS proxy. The same shape is returned
 * for 200 success AND 409 conflict (recalled / withdrawn / already-supplied);
 * callers read `ok` + `state` + `warning` to classify, never an exception.
 */
export interface HmvsPackResponse {
  /** True iff the upstream registry returned 200 and the pack is dispensable. */
  ok: boolean;
  /** Lifecycle state of the pack: "Active", "Supplied", or null on a hard error. */
  state: HmvsState | string | null;
  /** Pack state echoed back on a 409 invalid-transition response. */
  currentState: string | null;
  gtin: string;
  serial: string;
  /** Free-text upstream operation code (e.g. NMVS_OK, NMVS_NC_PCK_22). */
  operationCode: string | null;
  /** National healthcare reimbursement number (κωδικός ΕΟΦ). Null when absent. */
  nhrn: string | null;
  /** True iff the pack is registered in another country's NMVS. */
  isIntermarket: boolean;
  /** Pharmacy-facing informational text from the registry. */
  information: string | null;
  /**
   * Pharmacy-facing warning text — populated when the pack is BLOCKED from
   * dispense (recalled, withdrawn, expired, already supplied). Show this to
   * the pharmacist so they see WHY the verification did not pass.
   */
  warning: string | null;
  /** Product label echoed by the registry — for the pharmacist's eyeball check. */
  productName: string | null;
  /** Batch-level state ("Active", "Recalled", "Withdrawn", …). */
  batchState: string | null;
  /** Upstream alert identifier raised by the registry, when applicable. */
  alertId: string | null;
  /** True when the backend store-and-forward queued the intent for later replay. */
  queued: boolean;
  /** Seconds to back off when the upstream throttled the request (429 Retry-After). */
  retryAfterSeconds: number | null;
}

function packUrl({ gtin, serial, batch, expiry }: HmvsPackKey): string {
  if (!gtin || !serial || !batch || !expiry) {
    throw new ApiError(400, "Missing GS1 field for HMVS operation (gtin/serial/batch/expiry).");
  }
  const qs = new URLSearchParams({ batch, expiry });
  return `${API_BASE}/pharmapi/hmvs/product/gs1/${encodeURIComponent(gtin)}/pack/${encodeURIComponent(serial)}?${qs}`;
}

function normalise(body: Record<string, unknown>, fallback: HmvsPackKey): HmvsPackResponse {
  return {
    ok: Boolean(body.ok),
    state: (body.state as HmvsPackResponse["state"]) ?? null,
    currentState: (body.currentState as string | null) ?? null,
    gtin: typeof body.gtin === "string" ? body.gtin : fallback.gtin,
    serial: typeof body.serial === "string" ? body.serial : fallback.serial,
    operationCode: (body.operationCode as string | null) ?? null,
    nhrn: (body.nhrn as string | null) ?? null,
    isIntermarket: Boolean(body.isIntermarket),
    information: (body.information as string | null) ?? null,
    warning: (body.warning as string | null) ?? null,
    productName: (body.productName as string | null) ?? null,
    batchState: (body.batchState as string | null) ?? null,
    alertId: (body.alertId as string | null) ?? null,
    queued: Boolean(body.queued),
    retryAfterSeconds: (body.retryAfterSeconds as number | null) ?? null,
  };
}

/**
 * Parse a backend HMVS response into HmvsPackResponse.
 *
 * The backend returns the SAME structured shape on 200 (success) and on 4xx
 * conflicts where the upstream registry sent a populated body — for 4xx the
 * shape lives under FastAPI's `detail` field. Both are absorbed here. Only
 * transport / auth / 5xx without a structured body throws ApiError.
 */
async function parseHmvsResponse(r: Response, pack: HmvsPackKey): Promise<HmvsPackResponse> {
  const data = await r.json().catch(() => null);
  if (r.ok && data && typeof data === "object") {
    return normalise(data as Record<string, unknown>, pack);
  }
  const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : null;
  if (detail && typeof detail === "object") {
    return normalise(detail as Record<string, unknown>, pack);
  }
  const message = typeof detail === "string" && detail.trim() ? detail : `HTTP ${r.status}`;
  throw new ApiError(r.status, message);
}

/**
 * Verify a scanned pack against the HMVS registry.
 *
 * Maps to: GET /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?batch={batch}&expiry={YYMMDD}
 */
export async function hmvsVerify(pack: HmvsPackKey): Promise<HmvsPackResponse> {
  const r = await fetch(packUrl(pack), { credentials: "include" });
  return parseHmvsResponse(r, pack);
}

/**
 * Decommission (supply) a scanned pack — the normal dispense outcome.
 *
 * Maps to: PATCH /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?… body { state: "Supplied" }
 */
export async function hmvsDecommission(pack: HmvsPackKey): Promise<HmvsPackResponse> {
  const r = await fetch(packUrl(pack), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ state: "Supplied" }),
  });
  return parseHmvsResponse(r, pack);
}

/**
 * Reactivate a previously-decommissioned pack — reverses an erroneous supply
 * within the registry's allowed window.
 *
 * Maps to: PATCH /pharmapi/hmvs/product/gs1/{GTIN}/pack/{serial}?… body { state: "Active" }
 */
export async function hmvsReactivate(pack: HmvsPackKey): Promise<HmvsPackResponse> {
  const r = await fetch(packUrl(pack), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ state: "Active" }),
  });
  return parseHmvsResponse(r, pack);
}
