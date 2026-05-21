import type {
  ActiveAlert,
  AdrSort,
  DeliveryMethod,
  DeliveryMethodFilter,
  DocumentationListResponse,
  DocumentationRecord,
  GeneratedInstructions,
  InstructionsOptions,
  PatientCondition,
  PatientProfile,
  PatientRxHistoryRow,
  Prescription,
  PrescriptionMessage,
  QueueItem,
  SafetyCheck,
  SideEffectListResponse,
  SideEffectReport,
  SpcDetails,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function handle(r: Response): Promise<unknown> {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new ApiError(r.status, (data as { detail?: string }).detail ?? `HTTP ${r.status}`);
  }
  return data;
}

export interface LoginResponse {
  pharmacist_name: string;
  pharmacy: string;
  pharmacist_id: string;
  pharmacy_id: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  return handle(r) as Promise<LoginResponse>;
}

export async function logout(): Promise<void> {
  const r = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  await handle(r);
}

export interface MeResponse {
  email: string;
  name: string;
  pharmacy: string;
  pharmacist_id: string;
  pharmacy_id: string;
}

export async function me(): Promise<MeResponse> {
  const r = await fetch(`${API_BASE}/auth/me`, { credentials: "include" });
  return handle(r) as Promise<MeResponse>;
}

export async function getPrescription(rxId: string): Promise<Prescription> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}`, {
    credentials: "include",
  });
  return handle(r) as Promise<Prescription>;
}

export async function listPrescriptions(): Promise<QueueItem[]> {
  const r = await fetch(`${API_BASE}/prescriptions`, { credentials: "include" });
  const data = (await handle(r)) as { items?: QueueItem[] };
  if (!Array.isArray(data?.items)) {
    throw new ApiError(
      0,
      "Unexpected response from /prescriptions (missing 'items' array). Is the API running and proxied?",
    );
  }
  return data.items;
}

export async function getNextPrescription(): Promise<QueueItem> {
  const r = await fetch(`${API_BASE}/prescriptions/next`, { credentials: "include" });
  return handle(r) as Promise<QueueItem>;
}

export async function getSpc(atcCode: string): Promise<SpcDetails> {
  const r = await fetch(`${API_BASE}/spc/${encodeURIComponent(atcCode)}`, {
    credentials: "include",
  });
  const data = (await handle(r)) as Partial<SpcDetails>;
  if (
    !data ||
    typeof data.atcCode !== "string" ||
    !Array.isArray(data.contraindications) ||
    !Array.isArray(data.majorInteractions)
  ) {
    throw new ApiError(
      0,
      `Unexpected response from /spc/${atcCode} (missing required fields). Is the API running and proxied?`,
    );
  }
  return data as SpcDetails;
}

export async function getSafetyChecks(rxId: string): Promise<SafetyCheck[]> {
  const r = await fetch(`${API_BASE}/safety-checks/${encodeURIComponent(rxId)}`, {
    credentials: "include",
  });
  const data = (await handle(r)) as { rxId?: string; checks?: SafetyCheck[] };
  if (!Array.isArray(data?.checks)) {
    throw new ApiError(
      0,
      "Unexpected response from /safety-checks (missing 'checks' array). Is the API running and proxied?",
    );
  }
  return data.checks;
}

export async function getActiveAlerts(): Promise<ActiveAlert[]> {
  const r = await fetch(`${API_BASE}/alerts/active`, { credentials: "include" });
  const data = await handle(r);
  if (!Array.isArray(data)) {
    throw new ApiError(
      0,
      "Unexpected response from /alerts/active. Is the API running and proxied?",
    );
  }
  return data.map((a) => ({
    id: a.id,
    type: a.checkType,
    description: a.message,
    rxId: a.rxId ?? null,
    createdAt: a.createdAt ?? null,
  }));
}

export async function approvePrescription(
  rxId: string,
): Promise<{ success: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/prescriptions/${encodeURIComponent(rxId)}/approve`, {
    method: "POST",
    credentials: "include",
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
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  return handle(r) as Promise<PrescriptionPatchResponse>;
}

export async function notifyPhysician(
  rxId: string,
  message: string,
): Promise<{ success: boolean; delivered: boolean }> {
  const r = await fetch(`${API_BASE}/notifications/physician`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ rxId, message }),
  });
  return handle(r) as Promise<{ success: boolean; delivered: boolean }>;
}

export async function getMessages(rxId: string): Promise<PrescriptionMessage[]> {
  const r = await fetch(`${API_BASE}/messages?rxId=${encodeURIComponent(rxId)}`, {
    credentials: "include",
  });
  const data = (await handle(r)) as { items?: PrescriptionMessage[] };
  if (!Array.isArray(data?.items)) {
    throw new ApiError(
      0,
      "Unexpected response from /messages (missing 'items' array). Is the API running and proxied?",
    );
  }
  return data.items;
}

export async function sendMessage(
  to: string,
  rxId: string,
  body: string,
): Promise<PrescriptionMessage> {
  const r = await fetch(`${API_BASE}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ to, rxId, body }),
  });
  return handle(r) as Promise<PrescriptionMessage>;
}

export async function listDocumentation(
  params: {
    q?: string;
    method?: DeliveryMethodFilter;
  } = {},
): Promise<DocumentationListResponse> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.method && params.method !== "ALL") qs.set("method", params.method);
  const r = await fetch(`${API_BASE}/documentation${qs.toString() ? `?${qs}` : ""}`, {
    credentials: "include",
  });
  const data = (await handle(r)) as Partial<DocumentationListResponse>;
  if (!Array.isArray(data?.items) || !data.stats || typeof data.total !== "number") {
    throw new ApiError(
      0,
      "Unexpected response from /documentation. Is the API running and proxied?",
    );
  }
  return data as DocumentationListResponse;
}

export async function getDocumentationRecord(id: string): Promise<DocumentationRecord> {
  const r = await fetch(`${API_BASE}/documentation/${encodeURIComponent(id)}`, {
    credentials: "include",
  });
  return handle(r) as Promise<DocumentationRecord>;
}

async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const r = await fetch(url, { credentials: "include" });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new ApiError(r.status, (data as { detail?: string }).detail ?? `HTTP ${r.status}`);
  }
  const blob = await r.blob();
  const filename =
    parseContentDispositionFilename(r.headers.get("content-disposition")) ?? fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revocation so Safari has time to start the download.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const utf8 = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

export type ExportFormat = "pdf" | "csv";

export async function exportDocumentation(
  params: { q?: string; method?: DeliveryMethodFilter; format?: ExportFormat } = {},
): Promise<void> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.method && params.method !== "ALL") qs.set("method", params.method);
  const fmt: ExportFormat = params.format ?? "pdf";
  qs.set("format", fmt);
  const url = `${API_BASE}/documentation/export?${qs.toString()}`;
  const today = new Date().toISOString().slice(0, 10);
  await downloadFile(url, `PharmAssist_DocumentationLog_${today}.${fmt}`);
}

export async function exportDocumentationRecord(
  id: string,
  format: ExportFormat = "pdf",
): Promise<void> {
  const url = `${API_BASE}/documentation/${encodeURIComponent(id)}/export?format=${format}`;
  await downloadFile(url, `${id}.${format}`);
}

export async function listSideEffects(
  params: { q?: string; sort?: AdrSort } = {},
): Promise<SideEffectListResponse> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.sort) qs.set("sort", params.sort);
  const r = await fetch(`${API_BASE}/side-effects${qs.toString() ? `?${qs}` : ""}`, {
    credentials: "include",
  });
  const data = (await handle(r)) as Partial<SideEffectListResponse>;
  if (!Array.isArray(data?.items) || !data.stats) {
    throw new ApiError(
      0,
      "Unexpected response from /side-effects. Is the API running and proxied?",
    );
  }
  return data as SideEffectListResponse;
}

export async function flagSideEffect(reportId: string): Promise<{
  success: boolean;
  status: SideEffectReport["status"];
  previousStatus: SideEffectReport["status"];
}> {
  const r = await fetch(`${API_BASE}/side-effects/${encodeURIComponent(reportId)}/flag`, {
    method: "POST",
    credentials: "include",
  });
  return handle(r) as Promise<{
    success: boolean;
    status: SideEffectReport["status"];
    previousStatus: SideEffectReport["status"];
  }>;
}

export async function getPatient(patientId: string): Promise<PatientProfile> {
  const r = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}`, {
    credentials: "include",
  });
  return handle(r) as Promise<PatientProfile>;
}

export async function getPatientPrescriptions(patientId: string): Promise<PatientRxHistoryRow[]> {
  const r = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}/prescriptions`, {
    credentials: "include",
  });
  const data = (await handle(r)) as { items?: PatientRxHistoryRow[] };
  if (!Array.isArray(data?.items)) {
    throw new ApiError(0, `Unexpected response from /patients/${patientId}/prescriptions.`);
  }
  return data.items;
}

export async function getPatientSideEffects(patientId: string): Promise<SideEffectReport[]> {
  const r = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}/side-effects`, {
    credentials: "include",
  });
  const data = (await handle(r)) as { items?: SideEffectReport[] };
  if (!Array.isArray(data?.items)) {
    throw new ApiError(0, `Unexpected response from /patients/${patientId}/side-effects.`);
  }
  return data.items;
}

export async function getPatientConditions(patientId: string): Promise<PatientCondition[]> {
  const r = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}/conditions`, {
    credentials: "include",
  });
  const data = (await handle(r)) as Promise<PatientCondition[]>;
  if (!Array.isArray(data)) {
    throw new ApiError(0, `Unexpected response from /patients/${patientId}/conditions.`);
  }
  return data as PatientCondition[];
}

export async function generateInstructions(
  rxId: string,
  language: string,
  options: InstructionsOptions,
): Promise<GeneratedInstructions> {
  const r = await fetch(`${API_BASE}/instructions/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ rxId, language, options }),
  });
  return handle(r) as Promise<GeneratedInstructions>;
}

export async function sendInstructions(payload: {
  rxId: string;
  patientId?: string | null;
  content: string;
  method: DeliveryMethod;
}): Promise<{ success: boolean }> {
  const r = await fetch(`${API_BASE}/instructions/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  return handle(r) as Promise<{ success: boolean }>;
}

export async function createDocumentationEntry(payload: {
  rxId: string;
  instructions: string;
  language: string;
  method: DeliveryMethod;
  setting?: "Private" | "Hospital";
}): Promise<DocumentationRecord> {
  const r = await fetch(`${API_BASE}/documentation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  return handle(r) as Promise<DocumentationRecord>;
}

export async function apiGetInviteInfo(token: string): Promise<{
  pharmacy_name: string;
  pharmacy_address: string;
  email: string;
  expires_at: string;
}> {
  const res = await fetch(`${API_BASE}/auth/invite/${token}`, { credentials: "include" });
  if (res.status === 404) throw new Error("Invite not found");
  if (res.status === 410) throw new Error("Invite has expired or already been used");
  if (!res.ok) throw new Error("Failed to load invite");
  return res.json();
}

export async function apiAcceptInvite(data: {
  token: string;
  full_name: string;
  password: string;
  eof_licence_no: string;
  phone?: string;
  pharmapi_username: string;
  pharmapi_password: string;
}): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/accept-invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (res.status === 400) {
    const err = await res.json();
    throw new Error(err.detail || "ΗΔΥΚΑ credentials rejected");
  }
  if (res.status === 409) throw new Error("An account already exists for this email");
  if (res.status === 410) throw new Error("Invite has expired or already been used");
  if (!res.ok) throw new Error("Failed to create account");
}
