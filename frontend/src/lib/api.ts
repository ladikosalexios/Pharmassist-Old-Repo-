import type { ActiveAlert, Prescription, QueueItem, SafetyCheck } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function authHeaders(): Record<string, string> {
  const token = sessionStorage.getItem("pa_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle(r: Response): Promise<unknown> {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new ApiError(r.status, (data as { detail?: string }).detail ?? `HTTP ${r.status}`);
  }
  return data;
}

export interface LoginResponse {
  access_token: string;
  pharmacist_name: string;
  pharmacy: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return handle(r) as Promise<LoginResponse>;
}

export async function me(): Promise<{ email: string; name: string; pharmacy: string }> {
  const r = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() });
  return handle(r) as Promise<{ email: string; name: string; pharmacy: string }>;
}

export async function getPrescription(rxId: string): Promise<Prescription> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}`, {
    headers: authHeaders(),
  });
  return handle(r) as Promise<Prescription>;
}

export async function listPrescriptions(): Promise<QueueItem[]> {
  const r = await fetch(`${API_BASE}/prescriptions`, { headers: authHeaders() });
  const data = (await handle(r)) as { items?: QueueItem[] };
  if (!Array.isArray(data?.items)) {
    throw new ApiError(0, "Unexpected response from /prescriptions (missing 'items' array). Is the API running and proxied?");
  }
  return data.items;
}

export async function getSafetyChecks(rxId: string): Promise<SafetyCheck[]> {
  const r = await fetch(`${API_BASE}/safety-checks/${encodeURIComponent(rxId)}`, {
    headers: authHeaders(),
  });
  const data = (await handle(r)) as { rxId?: string; checks?: SafetyCheck[] };
  if (!Array.isArray(data?.checks)) {
    throw new ApiError(0, "Unexpected response from /safety-checks (missing 'checks' array). Is the API running and proxied?");
  }
  return data.checks;
}

export async function getActiveAlerts(): Promise<ActiveAlert[]> {
  const r = await fetch(`${API_BASE}/alerts/active`, { headers: authHeaders() });
  const data = (await handle(r)) as { alerts?: ActiveAlert[] };
  if (!Array.isArray(data?.alerts)) {
    throw new ApiError(0, "Unexpected response from /alerts/active (missing 'alerts' array). Is the API running and proxied?");
  }
  return data.alerts;
}

export async function approvePrescription(rxId: string): Promise<{ success: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handle(r) as Promise<{ success: boolean; status: string }>;
}

export type DiscrepancyType =
  | "dose_error"
  | "drug_drug_interaction"
  | "missing_info"
  | "suspected_forgery"
  | "other";

export interface FlagPayload {
  status: "flagged";
  discrepancy_type: DiscrepancyType;
  notes: string;
  notify_physician: boolean;
}

export interface PrescriptionPatchResponse {
  success: boolean;
  rxId: string;
  status: string;
  discrepancyType?: string | null;
  notes?: string | null;
  notifyPhysician?: boolean | null;
}

export async function patchPrescription(
  rxId: string,
  body: Partial<FlagPayload>,
): Promise<PrescriptionPatchResponse> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handle(r) as Promise<PrescriptionPatchResponse>;
}

export async function notifyPhysician(rxId: string, message: string): Promise<{ success: boolean; delivered: boolean }> {
  const r = await fetch(`${API_BASE}/notifications/physician`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ rxId, message }),
  });
  return handle(r) as Promise<{ success: boolean; delivered: boolean }>;
}
