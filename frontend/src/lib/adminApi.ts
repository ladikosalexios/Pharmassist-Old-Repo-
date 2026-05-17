/**
 * API client for the company admin portal (/admin/*).
 *
 * Mirrors lib/api.ts — reuses its `ApiError` class and the same
 * `credentials: "include"` cookie handling. The admin session rides on the
 * separate `pharmassist_admin_session` cookie issued by /admin/login.
 */

import { ApiError } from "./api";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function handle(r: Response): Promise<unknown> {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new ApiError(r.status, (data as { detail?: string }).detail ?? `HTTP ${r.status}`);
  }
  return data;
}

type QueryValue = string | number | boolean | undefined | null;

function qs(params: Record<string, QueryValue>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function get(path: string): Promise<unknown> {
  return handle(await fetch(`${API_BASE}${path}`, { credentials: "include" }));
}

async function post(path: string, body?: unknown): Promise<unknown> {
  return handle(
    await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      credentials: "include",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  );
}

// ── Types ──────────────────────────────────────────────────────────────────

/** /admin/login and /admin/me both return this shape. */
export interface AdminUser {
  staff_id: string;
  name: string;
  email: string;
  role: string;
}

export interface Pharmacy {
  id: string;
  name: string;
  pharmapi_unit_id: number;
  address: string | null;
  street_name: string | null;
  street_number: string | null;
  area: string | null;
  city: string | null;
  postal_code: string | null;
  phone: string | null;
  fax: string | null;
  email: string | null;
  geographic_region: string | null;
  accounting_category: string | null;
  is_branch: boolean;
  tax_id: string | null;
  active: boolean;
  created_at: string;
}

/** Fields collected when onboarding a brand-new pharmacy. */
export interface PharmacyCreate {
  name: string;
  pharmapi_unit_id: number;
  address?: string | null;
  street_name?: string | null;
  street_number?: string | null;
  area?: string | null;
  city?: string | null;
  postal_code?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  geographic_region?: string | null;
  accounting_category?: string | null;
  is_branch?: boolean;
  tax_id?: string | null;
}

export interface PharmacyListItem {
  id: string;
  name: string;
  city: string | null;
  pharmacist_count: number;
  pending_invite_count: number;
}

export interface PharmacyListResponse {
  items: PharmacyListItem[];
  total: number;
}

export interface Pharmacist {
  id: string;
  email: string;
  full_name: string;
  eof_licence_no: string;
  phone: string | null;
  role: string;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  status: "pending" | "accepted" | "expired";
  invite_url: string;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

export interface AuditLogEntry {
  id: number;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  actor_type: "staff" | "pharmacist" | "system";
  actor_name: string | null;
  occurred_at: string;
}

export interface PharmacyDetail {
  pharmacy: Pharmacy;
  pharmacists: Pharmacist[];
  invitations: Invitation[];
  audit: AuditLogEntry[];
}

export interface InviteResult {
  invite_url: string;
  expires_at: string;
  email: string;
}

// ── Auth ───────────────────────────────────────────────────────────────────

export async function adminLogin(email: string, password: string): Promise<AdminUser> {
  return post("/admin/login", { email, password }) as Promise<AdminUser>;
}

export async function adminLogout(): Promise<void> {
  await post("/admin/logout");
}

export async function adminMe(): Promise<AdminUser> {
  return get("/admin/me") as Promise<AdminUser>;
}

// ── Pharmacies ─────────────────────────────────────────────────────────────

export async function listPharmacies(
  params: { q?: string; limit?: number; offset?: number } = {},
): Promise<PharmacyListResponse> {
  return get(`/admin/pharmacies${qs(params)}`) as Promise<PharmacyListResponse>;
}

export async function getPharmacy(id: string): Promise<PharmacyDetail> {
  return get(`/admin/pharmacies/${id}`) as Promise<PharmacyDetail>;
}

// ── Onboarding ─────────────────────────────────────────────────────────────

export async function onboardPharmacy(
  pharmacistEmail: string,
  pharmacy: PharmacyCreate,
): Promise<InviteResult> {
  return post("/admin/invitations", {
    pharmacist_email: pharmacistEmail,
    pharmacy,
  }) as Promise<InviteResult>;
}
