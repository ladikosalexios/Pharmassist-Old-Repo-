import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangleIcon,
  AlertCircleIcon,
  AlertOctagonIcon,
  CheckCircleIcon,
  ClockIcon,
  FlagIcon,
  PhoneIcon,
  SearchIcon,
  SendIcon,
  UsersIcon,
} from "../components/Icons";
import { useToast } from "../components/Toast";
import { ApiError, flagSideEffect, listSideEffects, notifyPhysician } from "../lib/api";
import type {
  AdrSeverity,
  AdrSort,
  AdrStatus,
  SideEffectListResponse,
  SideEffectReport,
  SideEffectStats,
} from "../types";

// Mirror of the backend seed so the page still works when the API is down or
// hasn't yet been restarted to pick up the new /side-effects route. Mutations
// in fallback mode are local-only and reset on reload.
const FALLBACK_REPORTS: SideEffectReport[] = [
  {
    id: "ADR-2026-0009",
    patientId: "P001",
    patientName: "Maria Stavrou",
    patientPhone: "+30 694 312 3456",
    rxId: "RX2024-005",
    drugName: "Warfarin 5 mg",
    severity: "SEVERE",
    status: "ESCALATED",
    reportedAt: "2026-04-29T16:42:00+00:00",
    symptom: "Dark stools, dizziness on standing, gum bleeding after brushing teeth.",
    onset: "8 hours after the second dose",
  },
  {
    id: "ADR-2026-0008",
    patientId: "P004",
    patientName: "Eleni Papadopoulos",
    patientPhone: "+30 697 555 0142",
    rxId: "RX2024-002",
    drugName: "Warfarin 7.5 mg",
    severity: "MODERATE",
    status: "PENDING_REVIEW",
    reportedAt: "2026-04-28T11:05:00+00:00",
    symptom: "Persistent nosebleeds and unusual bruising on forearms.",
    onset: "Within 48 hours of dose increase",
  },
  {
    id: "ADR-2026-0007",
    patientId: "P010",
    patientName: "Sarah Johnson",
    patientPhone: "+30 698 011 2233",
    rxId: "RX2024-001",
    drugName: "Amoxicillin 500 mg",
    severity: "MILD",
    status: "PENDING_REVIEW",
    reportedAt: "2026-04-26T08:20:00+00:00",
    symptom: "Diffuse maculopapular rash on torso, no breathing difficulty.",
    onset: "Day 3 of antibiotic course",
  },
  {
    id: "ADR-2026-0006",
    patientId: "P012",
    patientName: "Dimitrios Konstantinou",
    patientPhone: "+30 698 555 7012",
    rxId: null,
    drugName: "Atorvastatin 20 mg",
    severity: "SEVERE",
    status: "EOF_REPORTED",
    reportedAt: "2026-04-22T19:14:00+00:00",
    symptom: "Generalised muscle pain, dark urine, ALT 5x upper limit.",
    onset: "Three weeks after starting therapy",
  },
  {
    id: "ADR-2026-0005",
    patientId: "P020",
    patientName: "Anna Kostas",
    patientPhone: "+30 697 999 0011",
    rxId: null,
    drugName: "Clopidogrel 75 mg",
    severity: "MODERATE",
    status: "ESCALATED",
    reportedAt: "2026-04-15T12:00:00+00:00",
    symptom: "Two episodes of melena, mild dyspnoea on exertion.",
    onset: "Two weeks into therapy",
  },
  {
    id: "ADR-2026-0004",
    patientId: "P031",
    patientName: "Nikos Vlachos",
    patientPhone: "+30 698 222 0099",
    rxId: null,
    drugName: "Metformin 1000 mg",
    severity: "MILD",
    status: "EOF_REPORTED",
    reportedAt: "2026-03-30T10:30:00+00:00",
    symptom: "Mild gastrointestinal upset and metallic taste.",
    onset: "First week of therapy",
  },
];

const SEVERITY_RANK: Record<AdrSeverity, number> = { MILD: 0, MODERATE: 1, SEVERE: 2 };
const STATUS_RANK: Record<AdrStatus, number> = { PENDING_REVIEW: 0, ESCALATED: 1, EOF_REPORTED: 2 };

function computeFallbackStats(reports: SideEffectReport[]): SideEffectStats {
  const s: SideEffectStats = { total: reports.length, pendingReview: 0, severe: 0, escalated: 0 };
  for (const r of reports) {
    if (r.status === "PENDING_REVIEW") s.pendingReview++;
    if (r.severity === "SEVERE") s.severe++;
    if (r.status === "ESCALATED") s.escalated++;
  }
  return s;
}

function applyFallbackFilters(
  reports: SideEffectReport[],
  q: string,
  sort: AdrSort,
): SideEffectReport[] {
  const needle = q.trim().toLowerCase();
  const out = needle
    ? reports.filter(
        (r) =>
          r.patientName.toLowerCase().includes(needle) ||
          r.drugName.toLowerCase().includes(needle) ||
          r.symptom.toLowerCase().includes(needle),
      )
    : [...reports];
  if (sort === "severity") {
    out.sort(
      (a, b) =>
        SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] ||
        b.reportedAt.localeCompare(a.reportedAt),
    );
  } else if (sort === "status") {
    out.sort(
      (a, b) =>
        STATUS_RANK[b.status] - STATUS_RANK[a.status] || b.reportedAt.localeCompare(a.reportedAt),
    );
  } else {
    out.sort((a, b) => b.reportedAt.localeCompare(a.reportedAt));
  }
  return out;
}

function nextStatus(s: AdrStatus): AdrStatus {
  if (s === "PENDING_REVIEW") return "ESCALATED";
  if (s === "ESCALATED") return "EOF_REPORTED";
  return s;
}

const SEVERITY_TONE: Record<AdrSeverity, string> = {
  MILD: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-400",
  MODERATE: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-400",
  SEVERE: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-400",
};

const SEVERITY_LABEL: Record<AdrSeverity, string> = {
  MILD: "Mild",
  MODERATE: "Moderate",
  SEVERE: "Severe",
};

const STATUS_STYLE: Record<AdrStatus, string> = {
  PENDING_REVIEW:
    "border border-amber-300 bg-white text-amber-800 dark:border-amber-500/30 dark:bg-transparent dark:text-amber-400",
  ESCALATED:
    "border border-red-300 bg-white text-red-800 dark:border-red-500/30 dark:bg-transparent dark:text-red-400",
  EOF_REPORTED: "border border-emerald-600 bg-emerald-600 text-white",
};

const STATUS_LABEL: Record<AdrStatus, string> = {
  PENDING_REVIEW: "Pending Review",
  ESCALATED: "Escalated",
  EOF_REPORTED: "EOF Reported",
};

const SORT_OPTIONS: { value: AdrSort; label: string }[] = [
  { value: "date", label: "Date Reported (newest)" },
  { value: "severity", label: "Severity" },
  { value: "status", label: "Status" },
];

export function SideEffects() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<AdrSort>("date");
  const [items, setItems] = useState<SideEffectReport[] | null>(null);
  const [stats, setStats] = useState<SideEffectStats>({
    total: 0,
    pendingReview: 0,
    severe: 0,
    escalated: 0,
  });
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [usingFallback, setUsingFallback] = useState(false);
  const [fallbackError, setFallbackError] = useState<string | null>(null);
  // Master copy of fallback data so flag mutations persist across re-fetches
  // while in fallback mode (until reload).
  const [fallbackMaster, setFallbackMaster] = useState<SideEffectReport[]>(() => [
    ...FALLBACK_REPORTS,
  ]);

  // Debounce search input.
  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    listSideEffects({ q: query || undefined, sort })
      .then((res: SideEffectListResponse) => {
        if (!active) return;
        setItems(res.items);
        setStats(res.stats);
        setUsingFallback(false);
        setFallbackError(null);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setUsingFallback(true);
        setFallbackError(e instanceof ApiError ? e.message : "API unreachable.");
        setItems(applyFallbackFilters(fallbackMaster, query, sort));
        setStats(computeFallbackStats(fallbackMaster));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, sort, fallbackMaster]);

  const statCards = useMemo(
    () => [
      {
        label: "Total Reports",
        value: stats.total,
        tone: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
        valueClass: "text-slate-900 dark:text-slate-100",
        Icon: AlertTriangleIcon,
      },
      {
        label: "Pending Review",
        value: stats.pendingReview,
        tone: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
        valueClass: "text-amber-700 dark:text-amber-400",
        Icon: ClockIcon,
      },
      {
        label: "Severe Cases",
        value: stats.severe,
        tone: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
        valueClass: "text-red-700 dark:text-red-400",
        Icon: AlertOctagonIcon,
      },
      {
        label: "Escalated",
        value: stats.escalated,
        tone: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
        valueClass: "text-blue-700 dark:text-blue-400",
        Icon: FlagIcon,
      },
    ],
    [stats],
  );

  function applyStatusUpdate(reportId: string, oldStatus: AdrStatus, newStatus: AdrStatus) {
    setItems((cur) =>
      cur ? cur.map((r) => (r.id === reportId ? { ...r, status: newStatus } : r)) : cur,
    );
    setStats((cur) => recomputeStats(cur, oldStatus, newStatus));
    if (usingFallback) {
      setFallbackMaster((cur) =>
        cur.map((r) => (r.id === reportId ? { ...r, status: newStatus } : r)),
      );
    }
  }

  async function onFlag(report: SideEffectReport) {
    if (report.status === "EOF_REPORTED") {
      toast(`${report.id} is already EOF reported.`, "info");
      return;
    }
    setBusyId(report.id);
    try {
      if (usingFallback) {
        const advanced = nextStatus(report.status);
        applyStatusUpdate(report.id, report.status, advanced);
        toast(`${report.id}: ${STATUS_LABEL[advanced]} (demo)`, "success");
      } else {
        const result = await flagSideEffect(report.id);
        applyStatusUpdate(report.id, report.status, result.status);
        toast(`${report.id}: ${STATUS_LABEL[result.status]}`, "success");
      }
    } catch (e) {
      toast(e instanceof ApiError ? `Flag failed: ${e.message}` : "Flag failed.", "error");
    } finally {
      setBusyId(null);
    }
  }

  async function onNotifyPhysician(report: SideEffectReport) {
    if (!report.rxId) {
      toast(`No prescription is linked to ${report.id}; cannot notify the physician.`, "warn");
      return;
    }
    setBusyId(report.id);
    try {
      if (usingFallback) {
        // No backend call — just acknowledge.
        toast(`Physician notification queued for ${report.rxId} (demo).`, "success");
      } else {
        await notifyPhysician(
          report.rxId,
          `Adverse reaction reported (${report.id}, severity ${SEVERITY_LABEL[report.severity]}): ${report.symptom} (onset ${report.onset}).`,
        );
        toast(`Physician notified for ${report.rxId}.`, "success");
      }
    } catch (e) {
      toast(
        e instanceof ApiError ? `Notification failed: ${e.message}` : "Notification failed.",
        "error",
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <div className="mb-7 flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
          <AlertTriangleIcon width={18} height={18} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            Side Effect Reports
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Patient-reported adverse drug reactions
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map(({ label, value, tone, valueClass, Icon }) => (
          <div key={label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-medium text-slate-500 dark:text-slate-400">
                  {label}
                </div>
                <div className={`mt-1 text-3xl font-bold ${valueClass}`}>
                  {loading ? "—" : value}
                </div>
              </div>
              <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone}`}>
                <Icon width={18} height={18} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Search + sort */}
      <div className="card mb-5 flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="relative flex-1 min-w-[220px]">
          <SearchIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500"
          />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by patient name, medication, or symptom..."
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as AdrSort)}
          className="rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-8 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          aria-label="Sort reports"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Fallback banner */}
      {usingFallback && !loading && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>
            Showing demo data — the side-effects API is unreachable. Mutations apply locally only.
            {fallbackError && (
              <span className="ml-1 text-amber-700/80 dark:text-amber-400/80">
                ({fallbackError})
              </span>
            )}
          </span>
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500 dark:text-slate-400">
          <span className="spinner text-brand-600" /> Loading reports…
        </div>
      ) : !items || items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500 dark:text-slate-400">
          No reports match your filters.
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <li key={r.id}>
              <ReportCard
                report={r}
                busy={busyId === r.id}
                onContact={() => {
                  if (!r.patientPhone) {
                    toast("No phone number on file for this patient.", "warn");
                    return;
                  }
                  window.location.href = `tel:${r.patientPhone}`;
                }}
                onNotify={() => onNotifyPhysician(r)}
                onFlag={() => onFlag(r)}
                onViewProfile={() => navigate(`/patients/${r.patientId}`)}
              />
            </li>
          ))}
        </ul>
      )}

      {/* Guidelines */}
      <div className="mt-8 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm text-blue-900 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-200">
        <div className="mb-2 flex items-center gap-2 font-semibold">
          <CheckCircleIcon width={16} height={16} className="text-blue-600 dark:text-blue-400" />{" "}
          Pharmacovigilance Guidelines
        </div>
        <ol className="list-decimal space-y-1.5 pl-5 leading-relaxed">
          <li>
            Severe adverse drug reactions must be reported to the EOF (Εθνικός Οργανισμός Φαρμάκων)
            within 24 hours of identification.
          </li>
          <li>
            Escalate any reaction that is life-threatening, results in hospitalisation, or causes
            persistent disability — regardless of suspected causality.
          </li>
          <li>
            Confirmed serious reactions are reported to the EOF via the national pharmacovigilance
            portal; keep the prescriber and patient informed at every stage.
          </li>
          <li>
            Document every step in the patient&apos;s record: symptom, onset, action taken, EOF
            reference number once issued.
          </li>
        </ol>
      </div>
    </div>
  );
}

interface ReportCardProps {
  report: SideEffectReport;
  busy: boolean;
  onContact: () => void;
  onNotify: () => void;
  onFlag: () => void;
  onViewProfile: () => void;
}

function ReportCard({ report, busy, onContact, onNotify, onFlag, onViewProfile }: ReportCardProps) {
  const flagLabel =
    report.status === "PENDING_REVIEW"
      ? "Flag for Pharmacovigilance"
      : report.status === "ESCALATED"
        ? "Report to EOF"
        : "EOF Reported";

  return (
    <article className="card p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {report.patientName}
            </h3>
            <span className={`chip ${SEVERITY_TONE[report.severity]}`}>
              {SEVERITY_LABEL[report.severity]}
            </span>
            <span className={`chip ${STATUS_STYLE[report.status]}`}>
              {STATUS_LABEL[report.status]}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-slate-500 dark:text-slate-400">
            {report.rxId ? (
              <Link
                to={`/prescription/${report.rxId}`}
                className="font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                {report.drugName}
              </Link>
            ) : (
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {report.drugName}
              </span>
            )}
            <span className="text-slate-400 dark:text-slate-500">·</span>
            <span>
              Patient ID:{" "}
              <span className="font-mono text-slate-700 dark:text-slate-300">
                {report.patientId}
              </span>
            </span>
            <span className="text-slate-400 dark:text-slate-500">·</span>
            <span>Reported {formatTimestamp(report.reportedAt)}</span>
          </div>
        </div>
      </header>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-500/30 dark:bg-amber-500/10">
          <div className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
            Reported Symptom
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-amber-900 dark:text-amber-200">
            {report.symptom}
          </p>
        </div>
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-500/30 dark:bg-blue-500/10">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-400">
            Time of Onset
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-blue-900 dark:text-blue-200">
            {report.onset}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onContact}
          disabled={!report.patientPhone}
          className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
          title={report.patientPhone ?? "No phone on file"}
        >
          <PhoneIcon /> Contact Patient
        </button>
        <button
          type="button"
          onClick={onNotify}
          disabled={busy || !report.rxId}
          className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {busy ? <span className="spinner" /> : <SendIcon />} Notify Physician
        </button>
        <button
          type="button"
          onClick={onFlag}
          disabled={busy || report.status === "EOF_REPORTED"}
          className="btn btn-amber disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {busy ? <span className="spinner" /> : <FlagIcon />} {flagLabel}
        </button>
        <button type="button" onClick={onViewProfile} className="btn btn-outline">
          <UsersIcon /> View Patient Profile
        </button>
      </div>
    </article>
  );
}

function recomputeStats(
  prev: { total: number; pendingReview: number; severe: number; escalated: number },
  oldStatus: AdrStatus,
  newStatus: AdrStatus,
): { total: number; pendingReview: number; severe: number; escalated: number } {
  if (oldStatus === newStatus) return prev;
  const next = { ...prev };
  if (oldStatus === "PENDING_REVIEW") next.pendingReview = Math.max(0, next.pendingReview - 1);
  if (oldStatus === "ESCALATED") next.escalated = Math.max(0, next.escalated - 1);
  if (newStatus === "PENDING_REVIEW") next.pendingReview += 1;
  if (newStatus === "ESCALATED") next.escalated += 1;
  return next;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
