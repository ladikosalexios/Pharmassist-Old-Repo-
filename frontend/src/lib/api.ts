import type { Prescription } from "../types";

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

export async function approvePrescription(rxId: string): Promise<{ success: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handle(r) as Promise<{ success: boolean; status: string }>;
}

export async function flagPrescription(
  rxId: string,
  reason: string,
): Promise<{ success: boolean; status: string; reason: string }> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}/flag`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reason }),
  });
  return handle(r) as Promise<{ success: boolean; status: string; reason: string }>;
}
