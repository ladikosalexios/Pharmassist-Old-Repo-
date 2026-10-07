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
  report_date: string | null;
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
    report_date: new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Athens",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
  };
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
