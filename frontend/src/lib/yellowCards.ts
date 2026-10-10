export interface Reaction {
  description: string;
  onset: string | null;
  onset_unknown: boolean;
  end: string | null;
  outcome: number;
}
export interface Medicine {
  name: string;
  lot: string;
  route: string;
  dose: string;
  start: string | null;
  end: string | null;
  indication: string;
}
export interface ReportData {
  initials: string;
  age: string;
  weight: string;
  height: string;
  sex: string;
  reactions: Reaction[];
  serious: boolean | null;
  seriousness: string[];
  death_date: string | null;
  death_cause: string;
  suspected: Medicine[];
  concomitant: Medicine[];
  observations: string;
  reporter_name: string;
  reporter_address: string;
  reporter_institution: string;
  reporter_phone: string;
  reporter_email: string;
  reporter_type: ReporterType;
  reporter_specialty: string;
  reporter_other: string;
  report_date: string | null;
}
// Every role the backend form accepts. PharmAssist offers only the pharmacist roles.
export type ReporterType =
  | "hospital_doctor"
  | "hospital_pharmacist"
  | "private_doctor"
  | "private_pharmacist"
  | "other";
export const REPORTER_TYPES: readonly ReporterType[] = [
  "hospital_doctor",
  "hospital_pharmacist",
  "private_doctor",
  "private_pharmacist",
  "other",
];
export const PHARMACIST_REPORTERS = ["private_pharmacist", "hospital_pharmacist"] as const;
export type PharmacistReporter = (typeof PHARMACIST_REPORTERS)[number];
export const isPharmacistReporter = (value: unknown): value is PharmacistReporter =>
  (PHARMACIST_REPORTERS as readonly unknown[]).includes(value);
type ReporterKey = "reporter_type" | "reporter_specialty" | "reporter_other";
// Drafts saved before the reporter role existed come back without these keys.
export type StoredReportData = Omit<ReportData, ReporterKey> &
  Partial<Pick<ReportData, ReporterKey>>;
const reporterDefaults: Pick<ReportData, ReporterKey> = {
  reporter_type: "private_pharmacist",
  reporter_specialty: "",
  reporter_other: "",
};
// Fill only absent keys: any key present in the draft, even null or unknown, overrides the default.
export function withReporterDefaults(data: StoredReportData): ReportData {
  return { ...reporterDefaults, ...data };
}
// Details a switch to a pharmacist role would remove, whatever the current role.
export function removedReporterDetails(
  data: ReportData,
): ["reporter_specialty" | "reporter_other", string][] {
  return (["reporter_specialty", "reporter_other"] as const)
    .filter((key) => Boolean(data[key]))
    .map((key) => [key, String(data[key])]);
}
export function asPharmacistReporter(data: ReportData, type: PharmacistReporter): ReportData {
  return { ...data, reporter_type: type, reporter_specialty: "", reporter_other: "" };
}
export interface Report {
  id: string;
  revision: number;
  data: ReportData;
}
export interface Signature {
  id: string;
  sha256: string;
}
export interface Preview {
  id: string;
  revision: number;
  signature_id: string;
  sha256: string;
  envelope: { from: string; to: string; reply_to: string; subject: string; body: string };
}
export interface Submission {
  id: string;
  preview_id: string;
  status: string;
  approved_at: string;
  failure_code: string | null;
}
export const medicine = (): Medicine => ({
  name: "",
  lot: "",
  route: "",
  dose: "",
  start: null,
  end: null,
  indication: "",
});
export const reaction = (): Reaction => ({
  description: "",
  onset: null,
  onset_unknown: false,
  end: null,
  outcome: 6,
});
export function emptyReport(name: string, email: string): ReportData {
  return {
    initials: "",
    age: "",
    weight: "",
    height: "",
    sex: "",
    reactions: [reaction()],
    serious: null,
    seriousness: [],
    death_date: null,
    death_cause: "",
    suspected: [medicine()],
    concomitant: [],
    observations: "",
    reporter_name: name,
    reporter_address: "",
    reporter_institution: "",
    reporter_phone: "",
    reporter_email: email,
    ...reporterDefaults,
    report_date: new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Athens",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
  };
}
// The local Mailpit inbox for captured test mail. A stack on other ports sets
// VITE_YELLOW_CARDS_MAILPIT_URL; unset, blank or non-http(s) values use the default.
export const DEFAULT_MAILPIT_URL = "http://127.0.0.1:8026";
export function mailpitUrl(value: unknown = import.meta.env.VITE_YELLOW_CARDS_MAILPIT_URL): string {
  const url = typeof value === "string" ? value.trim() : "";
  return /^https?:\/\/\S+$/i.test(url) ? url : DEFAULT_MAILPIT_URL;
}
export class YellowCardHttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "YellowCardHttpError";
  }
}

// Network failures, timeouts and server errors may occur after a committed send.
export function isDefiniteRejection(error: unknown): boolean {
  return (
    error instanceof YellowCardHttpError &&
    error.status >= 400 &&
    error.status < 500 &&
    error.status !== 408
  );
}

export async function yc<T>(path = "", method = "GET", body?: unknown, key?: string): Promise<T> {
  const multipart = body instanceof FormData;
  const response = await fetch(`/yellow-cards${path}`, {
    method,
    credentials: "include",
    headers: {
      ...(!multipart && body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    throw new YellowCardHttpError(
      response.status,
      typeof detail === "string"
        ? detail
        : detail?.missing
          ? `Συμπληρώστε: ${detail.missing.join(", ")}`
          : `Η ενέργεια απέτυχε (${response.status}). Ελέγξτε τα πεδία και δοκιμάστε ξανά.`,
    );
  }
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>);
}
