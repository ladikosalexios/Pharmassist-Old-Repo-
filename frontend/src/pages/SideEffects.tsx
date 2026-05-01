import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangleIcon, AlertCircleIcon, AlertOctagonIcon, CheckCircleIcon,
  ClockIcon, FlagIcon, PhoneIcon, SearchIcon, SendIcon, UsersIcon,
} from "../components/Icons";
import { useToast } from "../components/Toast";
import { ApiError, flagSideEffect, listSideEffects, notifyPhysician } from "../lib/api";
import type { AdrSeverity, AdrSort, AdrStatus, SideEffectReport } from "../types";

const SEVERITY_TONE: Record<AdrSeverity, string> = {
  MILD:     "bg-amber-100 text-amber-800",
  MODERATE: "bg-orange-100 text-orange-800",
  SEVERE:   "bg-red-100 text-red-800",
};

const SEVERITY_LABEL: Record<AdrSeverity, string> = {
  MILD:     "Mild",
  MODERATE: "Moderate",
  SEVERE:   "Severe",
};

const STATUS_STYLE: Record<AdrStatus, string> = {
  PENDING_REVIEW: "border border-amber-300 bg-white text-amber-800",
  ESCALATED:      "border border-red-300 bg-white text-red-800",
  EOF_REPORTED:   "border border-emerald-600 bg-emerald-600 text-white",
};

const STATUS_LABEL: Record<AdrStatus, string> = {
  PENDING_REVIEW: "Pending Review",
  ESCALATED:      "Escalated",
  EOF_REPORTED:   "EOF Reported",
};

const SORT_OPTIONS: { value: AdrSort; label: string }[] = [
  { value: "date",     label: "Date Reported (newest)" },
  { value: "severity", label: "Severity" },
  { value: "status",   label: "Status" },
];

export function SideEffects() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<AdrSort>("date");
  const [items, setItems] = useState<SideEffectReport[] | null>(null);
  const [stats, setStats] = useState({ total: 0, pendingReview: 0, severe: 0, escalated: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Debounce search input.
  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listSideEffects({ q: query || undefined, sort })
      .then((res) => {
        if (!active) return;
        setItems(res.items);
        setStats(res.stats);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load side-effect reports.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, sort]);

  const statCards = useMemo(() => [
    { label: "Total Reports",  value: stats.total,         tone: "bg-slate-100 text-slate-700",   valueClass: "text-slate-900",    Icon: AlertTriangleIcon },
    { label: "Pending Review", value: stats.pendingReview, tone: "bg-amber-100 text-amber-700",   valueClass: "text-amber-700",    Icon: ClockIcon },
    { label: "Severe Cases",   value: stats.severe,        tone: "bg-red-100 text-red-700",       valueClass: "text-red-700",      Icon: AlertOctagonIcon },
    { label: "Escalated",      value: stats.escalated,     tone: "bg-blue-100 text-blue-700",     valueClass: "text-blue-700",     Icon: FlagIcon },
  ], [stats]);

  async function onFlag(report: SideEffectReport) {
    if (report.status === "EOF_REPORTED") {
      toast(`${report.id} is already EOF reported.`, "info");
      return;
    }
    setBusyId(report.id);
    try {
      const result = await flagSideEffect(report.id);
      setItems((cur) => cur ? cur.map((r) => r.id === report.id ? { ...r, status: result.status } : r) : cur);
      // Recompute stats locally so the dashboard cards stay in sync.
      setStats((cur) => recomputeStats(cur, report.status, result.status));
      toast(`${report.id}: ${STATUS_LABEL[result.status]}`, "success");
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
      await notifyPhysician(
        report.rxId,
        `Adverse reaction reported (${report.id}, severity ${SEVERITY_LABEL[report.severity]}): ${report.symptom} (onset ${report.onset}).`,
      );
      toast(`Physician notified for ${report.rxId}.`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? `Notification failed: ${e.message}` : "Notification failed.", "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-7 flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
          <AlertTriangleIcon width={18} height={18} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Side Effect Reports</h1>
          <p className="mt-1 text-sm text-slate-500">Patient-reported adverse drug reactions</p>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map(({ label, value, tone, valueClass, Icon }) => (
          <div key={label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-medium text-slate-500">{label}</div>
                <div className={`mt-1 text-3xl font-bold ${valueClass}`}>{loading ? "—" : value}</div>
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
          <SearchIcon width={16} height={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by patient name, medication, or symptom..."
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          />
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as AdrSort)}
          className="rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-8 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          aria-label="Sort reports"
        >
          {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {/* List */}
      {error ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-brand-600" /> Loading reports…
        </div>
      ) : !items || items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">No reports match your filters.</div>
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
      <div className="mt-8 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm text-blue-900">
        <div className="mb-2 flex items-center gap-2 font-semibold">
          <CheckCircleIcon width={16} height={16} className="text-blue-600" /> Pharmacovigilance Guidelines
        </div>
        <ol className="list-decimal space-y-1.5 pl-5 leading-relaxed">
          <li>Severe adverse drug reactions must be reported to the EOF (Εθνικός Οργανισμός Φαρμάκων) within 24 hours of identification.</li>
          <li>Escalate any reaction that is life-threatening, results in hospitalisation, or causes persistent disability — regardless of suspected causality.</li>
          <li>Confirmed serious reactions are reported to the EOF via the national pharmacovigilance portal; keep the prescriber and patient informed at every stage.</li>
          <li>Document every step in the patient's record: symptom, onset, action taken, EOF reference number once issued.</li>
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
    report.status === "PENDING_REVIEW" ? "Flag for Pharmacovigilance" :
    report.status === "ESCALATED"      ? "Report to EOF" :
                                         "EOF Reported";

  return (
    <article className="card p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900">{report.patientName}</h3>
            <span className={`chip ${SEVERITY_TONE[report.severity]}`}>{SEVERITY_LABEL[report.severity]}</span>
            <span className={`chip ${STATUS_STYLE[report.status]}`}>{STATUS_LABEL[report.status]}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-slate-500">
            {report.rxId ? (
              <Link to={`/prescription/${report.rxId}`} className="font-medium text-brand-600 hover:underline">
                {report.drugName}
              </Link>
            ) : (
              <span className="font-medium text-slate-700">{report.drugName}</span>
            )}
            <span className="text-slate-400">·</span>
            <span>Patient ID: <span className="font-mono text-slate-700">{report.patientId}</span></span>
            <span className="text-slate-400">·</span>
            <span>Reported {formatTimestamp(report.reportedAt)}</span>
          </div>
        </div>
      </header>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">Reported Symptom</div>
          <p className="mt-1.5 text-sm leading-relaxed text-amber-900">{report.symptom}</p>
        </div>
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-700">Time of Onset</div>
          <p className="mt-1.5 text-sm leading-relaxed text-blue-900">{report.onset}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={onContact} disabled={!report.patientPhone} className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed" title={report.patientPhone ?? "No phone on file"}>
          <PhoneIcon /> Contact Patient
        </button>
        <button type="button" onClick={onNotify} disabled={busy || !report.rxId} className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed">
          {busy ? <span className="spinner" /> : <SendIcon />} Notify Physician
        </button>
        <button type="button" onClick={onFlag} disabled={busy || report.status === "EOF_REPORTED"} className="btn btn-amber disabled:opacity-60 disabled:cursor-not-allowed">
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
  if (oldStatus === "ESCALATED")      next.escalated     = Math.max(0, next.escalated - 1);
  if (newStatus === "PENDING_REVIEW") next.pendingReview += 1;
  if (newStatus === "ESCALATED")      next.escalated     += 1;
  return next;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
