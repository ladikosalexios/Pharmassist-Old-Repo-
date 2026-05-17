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

async function patch(path: string, body: unknown): Promise<unknown> {
  return handle(
    await fetch(`${API_BASE}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    }),
  );
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface ListResponse<T> {
  items: T[];
  total: number;
}

// `type` (not `interface`) so it carries an implicit index signature and can
// be passed to qs()'s Record<string, QueryValue> parameter.
export type ListParams = {
  q?: string;
  active?: boolean;
  limit?: number;
  offset?: number;
};

/** /admin/login and /admin/me both return this shape. */
export interface AdminUser {
  staff_id: string;
  name: string;
  email: string;
  role: string;
}

export interface Invitation {
  id: string;
  email: string;
  pharmacy_id: string;
  pharmacy_name: string;
  status: "pending" | "accepted" | "expired";
  invite_url: string;
  invited_by_name: string | null;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

export interface InviteResult {
  invite_url: string;
  expires_at: string;
  email: string;
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

export type PharmacyUpdate = Partial<PharmacyCreate> & { active?: boolean };

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

export interface Staff {
  id: string;
  email: string;
  full_name: string;
  role: string;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface StaffCreate {
  email: string;
  full_name: string;
  password: string;
}

export interface Drug {
  id: string;
  gns_code: string;
  atc_code: string;
  atc_class: string;
  name_gr: string;
  name_en: string | null;
  interaction_group: string | null;
  active: boolean;
}

export interface DrugCreate {
  gns_code: string;
  atc_code: string;
  atc_class: string;
  name_gr: string;
  name_en?: string | null;
  interaction_group?: string | null;
}

export type DrugUpdate = Partial<DrugCreate> & { active?: boolean };

export interface SafetyRule {
  id: string;
  rule_code: string;
  check_type: string;
  severity: string;
  message_en: string;
  trigger_atc: string | null;
  trigger_condition_code: string | null;
  conflicting_atc: string | null;
  details_en: string | null;
  recommended_action_en: string | null;
  active: boolean;
}

export interface SafetyRuleCreate {
  rule_code: string;
  check_type: string;
  severity: string;
  message_en: string;
  trigger_atc?: string | null;
  trigger_condition_code?: string | null;
  conflicting_atc?: string | null;
  details_en?: string | null;
  recommended_action_en?: string | null;
}

export type SafetyRuleUpdate = Partial<SafetyRuleCreate> & { active?: boolean };

export interface DemoSeedResult {
  pharmacy_id: string;
  patient_conditions: number;
  adr_reports: number;
  documentation_logs: number;
}

export interface AuditLogEntry {
  id: number;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  actor_type: "staff" | "pharmacist" | "system";
  actor_name: string | null;
  pharmacy_name: string | null;
  response_code: string | null;
  ip_address: string | null;
  request_body: Record<string, unknown> | null;
  occurred_at: string;
}

export type AuditLogParams = {
  action?: string;
  resource_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
};

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

// ── Invitations ────────────────────────────────────────────────────────────

export async function listInvitations(
  params: { status?: string; q?: string; limit?: number; offset?: number } = {},
): Promise<ListResponse<Invitation>> {
  return get(`/admin/invitations${qs(params)}`) as Promise<ListResponse<Invitation>>;
}

export async function createInvitation(email: string, pharmacyId: string): Promise<InviteResult> {
  return post("/admin/invitations", {
    email,
    pharmacy_id: pharmacyId,
  }) as Promise<InviteResult>;
}

export async function revokeInvitation(id: string): Promise<void> {
  await post(`/admin/invitations/${id}/revoke`);
}

// ── Pharmacies ─────────────────────────────────────────────────────────────

export async function listPharmacies(params: ListParams = {}): Promise<ListResponse<Pharmacy>> {
  return get(`/admin/pharmacies${qs(params)}`) as Promise<ListResponse<Pharmacy>>;
}

export async function getPharmacy(id: string): Promise<Pharmacy> {
  return get(`/admin/pharmacies/${id}`) as Promise<Pharmacy>;
}

export async function createPharmacy(body: PharmacyCreate): Promise<Pharmacy> {
  return post("/admin/pharmacies", body) as Promise<Pharmacy>;
}

export async function updatePharmacy(id: string, body: PharmacyUpdate): Promise<Pharmacy> {
  return patch(`/admin/pharmacies/${id}`, body) as Promise<Pharmacy>;
}

// ── Pharmacists ────────────────────────────────────────────────────────────

export async function listPharmacists(params: ListParams = {}): Promise<ListResponse<Pharmacist>> {
  return get(`/admin/pharmacists${qs(params)}`) as Promise<ListResponse<Pharmacist>>;
}

export async function activatePharmacist(id: string): Promise<Pharmacist> {
  return post(`/admin/pharmacists/${id}/activate`) as Promise<Pharmacist>;
}

export async function deactivatePharmacist(id: string): Promise<Pharmacist> {
  return post(`/admin/pharmacists/${id}/deactivate`) as Promise<Pharmacist>;
}

// ── Staff ──────────────────────────────────────────────────────────────────

export async function listStaff(params: ListParams = {}): Promise<ListResponse<Staff>> {
  return get(`/admin/staff${qs(params)}`) as Promise<ListResponse<Staff>>;
}

export async function createStaff(body: StaffCreate): Promise<Staff> {
  return post("/admin/staff", body) as Promise<Staff>;
}

export async function activateStaff(id: string): Promise<Staff> {
  return post(`/admin/staff/${id}/activate`) as Promise<Staff>;
}

export async function deactivateStaff(id: string): Promise<Staff> {
  return post(`/admin/staff/${id}/deactivate`) as Promise<Staff>;
}

// ── Drug catalog ───────────────────────────────────────────────────────────

export async function listDrugs(params: ListParams = {}): Promise<ListResponse<Drug>> {
  return get(`/admin/drugs${qs(params)}`) as Promise<ListResponse<Drug>>;
}

export async function createDrug(body: DrugCreate): Promise<Drug> {
  return post("/admin/drugs", body) as Promise<Drug>;
}

export async function updateDrug(id: string, body: DrugUpdate): Promise<Drug> {
  return patch(`/admin/drugs/${id}`, body) as Promise<Drug>;
}

// ── Safety rules ───────────────────────────────────────────────────────────

export async function listSafetyRules(params: ListParams = {}): Promise<ListResponse<SafetyRule>> {
  return get(`/admin/safety-rules${qs(params)}`) as Promise<ListResponse<SafetyRule>>;
}

export async function createSafetyRule(body: SafetyRuleCreate): Promise<SafetyRule> {
  return post("/admin/safety-rules", body) as Promise<SafetyRule>;
}

export async function updateSafetyRule(id: string, body: SafetyRuleUpdate): Promise<SafetyRule> {
  return patch(`/admin/safety-rules/${id}`, body) as Promise<SafetyRule>;
}

// ── Demo seeder ────────────────────────────────────────────────────────────

export async function seedDemoData(pharmacyId: string): Promise<DemoSeedResult> {
  return post("/admin/demo/seed", { pharmacy_id: pharmacyId }) as Promise<DemoSeedResult>;
}

// ── Audit log ──────────────────────────────────────────────────────────────

export async function listAuditLogs(
  params: AuditLogParams = {},
): Promise<ListResponse<AuditLogEntry>> {
  return get(`/admin/audit-logs${qs(params)}`) as Promise<ListResponse<AuditLogEntry>>;
}
