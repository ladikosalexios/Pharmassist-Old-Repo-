import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangleIcon,
  AlertCircleIcon,
  AlertOctagonIcon,
  CheckCircleIcon,
  ClockIcon,
  FlagIcon,
  InfoIcon,
  PlusIcon,
  SearchIcon,
  BarcodeIcon,
  FileTextIcon,
  CheckIcon,
} from "../components/Icons";
import { useToast } from "../components/Toast";
import {
  ApiError,
  createSideEffect,
  flagSideEffect,
  listSideEffects,
  notifyPhysician,
} from "../lib/api";
import type {
  AdrSeverity,
  AdrSort,
  AdrStatus,
  SideEffectListResponse,
  SideEffectReport,
  SideEffectStats,
} from "../types";

// ── fallback data ─────────────────────────────────────────────────────────────

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

const RECENT_PATIENTS = FALLBACK_REPORTS.slice(0, 3).map((r) => r.patientName);

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

function recomputeStats(
  prev: SideEffectStats,
  oldStatus: AdrStatus,
  newStatus: AdrStatus,
): SideEffectStats {
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
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

// ── severity / status display ─────────────────────────────────────────────────

const SEV_TONE: Record<AdrSeverity, string> = {
  MILD: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  MODERATE: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  SEVERE: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-400",
};
const SEV_BTN: Record<string, string> = {
  Severe:
    "border-red-300 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/15 dark:text-red-400",
  Moderate:
    "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/15 dark:text-amber-400",
  Mild: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-400",
};

const STATUS_TONE: Record<AdrStatus, string> = {
  PENDING_REVIEW: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  ESCALATED: "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300",
  EOF_REPORTED: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
};
const STATUS_LABEL: Record<AdrStatus, string> = {
  PENDING_REVIEW: "Draft",
  ESCALATED: "Submitted",
  EOF_REPORTED: "Acknowledged",
};
const SEVERITY_LABEL: Record<AdrSeverity, string> = {
  MILD: "Mild",
  MODERATE: "Moderate",
  SEVERE: "Severe",
};

// ── Step head ─────────────────────────────────────────────────────────────────

function StepHead({ n, title, sub }: { n: string; title: string; sub?: string }) {
  return (
    <div className="mb-3 flex items-start gap-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[12px] font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
        {n}
      </span>
      <div>
        <h3 className="text-[14px] font-bold text-slate-900 dark:text-slate-100">{title}</h3>
        {sub && <p className="text-[12px] text-slate-500 dark:text-slate-400">{sub}</p>}
      </div>
    </div>
  );
}

// ── Report form ───────────────────────────────────────────────────────────────

interface ReportFormProps {
  onSubmitted: (report: SideEffectReport) => void;
  submittedRef: string | null;
}

function ReportForm({ onSubmitted, submittedRef }: ReportFormProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [patient, setPatient] = useState("");
  const [med, setMed] = useState("");
  const [sev, setSev] = useState("");
  const [onset, setOnset] = useState("");
  const [phase, setPhase] = useState<"during" | "after">("during");
  const [symptoms, setSymptoms] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [cause, setCause] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const commonSymptoms = useMemo(
    () => [
      t("reports.symptomRash"),
      t("reports.symptomNausea"),
      t("reports.symptomVomiting"),
      t("reports.symptomItching"),
      t("reports.symptomDizziness"),
      t("reports.symptomHeadache"),
      t("reports.symptomDyspnoea"),
      t("reports.symptomEdema"),
      t("reports.symptomDiarrhea"),
      t("reports.symptomAngioedema"),
    ],
    [t],
  );

  const togglePick = (s: string) =>
    setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]));

  const valid = patient.trim() && med.trim() && sev && (symptoms.trim() || picked.length > 0);

  async function handleSubmit() {
    if (!valid) return;
    setSubmitting(true);
    const severityMap: Record<string, AdrSeverity> = {
      Mild: "MILD",
      Moderate: "MODERATE",
      Severe: "SEVERE",
    };
    const symptom = [symptoms.trim(), ...picked].filter(Boolean).join("; ");
    try {
      const report = await createSideEffect({
        patientName: patient,
        drugName: med,
        severity: severityMap[sev] ?? "MILD",
        symptom,
        onset: onset || phase,
      });
      onSubmitted(report);
    } catch (e) {
      // Optimistic local prepend when backend endpoint not yet available
      if (e instanceof ApiError && e.status === 501) {
        const optimistic: SideEffectReport = {
          id: `ADR-LOCAL-${Date.now()}`,
          patientId: "",
          patientName: patient,
          patientPhone: null,
          rxId: null,
          drugName: med,
          severity: (severityMap[sev] as AdrSeverity) ?? "MILD",
          status: "PENDING_REVIEW",
          reportedAt: new Date().toISOString(),
          symptom,
          onset: onset || phase,
        };
        onSubmitted(optimistic);
        toast("Report saved locally — will sync when the backend endpoint is available.", "info");
      } else {
        toast(e instanceof ApiError ? e.message : "Submission failed. Please try again.", "error");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (submittedRef) {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3.5 animate-fade-in dark:border-emerald-500/30 dark:bg-emerald-500/10">
        <div className="flex items-start gap-3">
          <CheckCircleIcon
            width={20}
            height={20}
            className="mt-0.5 text-emerald-600 shrink-0 dark:text-emerald-400"
          />
          <div>
            <div className="text-[14px] font-bold text-emerald-800 dark:text-emerald-200">
              {t("reports.submittedTitle")}
            </div>
            <div className="mt-0.5 text-[12.5px] text-emerald-700 dark:text-emerald-400">
              {t("reports.submittedRef", { ref: submittedRef })}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        {/* 1 — Patient */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
          <StepHead n="1" title={t("reports.step1Title")} sub={t("reports.step1Sub")} />
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500">
              <SearchIcon width={16} height={16} />
            </span>
            <input
              value={patient}
              onChange={(e) => setPatient(e.target.value)}
              placeholder={t("reports.searchPatient")}
              className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-[13.5px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {RECENT_PATIENTS.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setPatient(r)}
                className={`max-w-[180px] truncate rounded-full border px-3 py-1 text-[12px] font-medium transition-colors ${
                  patient === r
                    ? "border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-500/30 dark:bg-brand-500/15 dark:text-brand-300"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-800/60"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        {/* 2 — Medicine */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
          <StepHead n="2" title={t("reports.step2Title")} sub={t("reports.step2Sub")} />
          <div className="flex gap-2.5">
            <div className="relative flex-1">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500">
                <SearchIcon width={16} height={16} />
              </span>
              <input
                value={med}
                onChange={(e) => setMed(e.target.value)}
                placeholder={t("reports.searchMed")}
                className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-[13.5px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              />
            </div>
            <button
              type="button"
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[12.5px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-800/60"
            >
              <BarcodeIcon width={15} height={15} /> {t("reports.scan")}
            </button>
          </div>
          {med && (
            <p className="mono mt-2 text-[11.5px] text-slate-400 dark:text-slate-500">
              {t("reports.autofillNote")}
            </p>
          )}
        </div>

        {/* 3 — Reaction */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
          <StepHead n="3" title={t("reports.step3Title")} />
          <div className="space-y-4">
            {/* severity */}
            <div>
              <label className="mb-1.5 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
                {t("reports.severityLabel")}
              </label>
              <div className="flex gap-2">
                {(["Mild", "Moderate", "Severe"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSev(s)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-[13px] font-semibold transition-colors ${
                      sev === s
                        ? SEV_BTN[s]
                        : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400 dark:hover:bg-slate-800/60"
                    }`}
                  >
                    {t(`reports.severity${s}`)}
                  </button>
                ))}
              </div>
            </div>

            {/* onset + timing */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
                  {t("reports.onsetDate")}
                </label>
                <input
                  type="date"
                  value={onset}
                  onChange={(e) => setOnset(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
                  {t("reports.timing")}
                </label>
                <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-800/50">
                  {(["during", "after"] as const).map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setPhase(v)}
                      className={`flex-1 rounded-md px-2 py-1.5 text-[12px] font-medium transition-colors ${
                        phase === v
                          ? "bg-white text-brand-700 shadow-card dark:bg-slate-900 dark:text-brand-300"
                          : "text-slate-500 dark:text-slate-400"
                      }`}
                    >
                      {t(`reports.timing${v.charAt(0).toUpperCase() + v.slice(1)}`)}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* symptoms */}
            <div>
              <label className="mb-1.5 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
                {t("reports.symptomsLabel")}
              </label>
              <textarea
                value={symptoms}
                onChange={(e) => setSymptoms(e.target.value)}
                rows={3}
                placeholder={t("reports.symptomsPlaceholder")}
                className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              />
              <div className="mt-2">
                <div className="mb-1.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
                  {t("reports.commonSymptoms")}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {commonSymptoms.map((s) => {
                    const on = picked.includes(s);
                    return (
                      <button
                        key={s}
                        type="button"
                        onClick={() => togglePick(s)}
                        className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[11.5px] font-medium transition-colors ${
                          on
                            ? "bg-brand-600 text-white"
                            : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-800/60"
                        }`}
                      >
                        {on ? (
                          <CheckIcon width={11} height={11} strokeWidth={3} />
                        ) : (
                          <PlusIcon width={11} height={11} />
                        )}
                        {s}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* causality */}
            <div>
              <label className="mb-1.5 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
                {t("reports.causality")}
              </label>
              <select
                value={cause}
                onChange={(e) => setCause(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              >
                <option value="">{t("reports.causalityPlaceholder")}</option>
                {(["Certain", "Probable", "Possible", "Unlikely"] as const).map((v) => (
                  <option key={v} value={v}>
                    {t(`reports.causality${v}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* 4 — Submit */}
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-800/60"
          >
            {t("reports.saveDraft")}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!valid || submitting}
            className="rounded-lg bg-brand-600 px-6 py-2.5 text-[13px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none dark:disabled:bg-slate-800 dark:disabled:text-slate-500"
          >
            {submitting ? <span className="spinner" /> : t("reports.step4Submit")}
          </button>
        </div>
      </div>

      {/* helper sidebar */}
      <aside>
        <div className="sticky top-4 rounded-xl border border-brand-100 bg-brand-50 p-5 dark:border-brand-500/20 dark:bg-brand-500/10">
          <div className="flex items-center gap-2 text-brand-700 dark:text-brand-300">
            <InfoIcon width={17} height={17} />
            <h3 className="text-[13.5px] font-bold">{t("reports.helperTitle")}</h3>
          </div>
          <ul className="mt-3 space-y-2.5 text-[12.5px] leading-relaxed text-slate-700 dark:text-slate-300">
            {[
              "Any suspected adverse reaction — even if causality is uncertain.",
              "Serious reactions: hospitalisation, life-threatening, congenital, persistent disability.",
              "Reactions to new medicines (≤5 years on market).",
              "Lack of efficacy, suspected counterfeits, or medication errors.",
              "Reactions during pregnancy or breastfeeding.",
            ].map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-500 dark:bg-brand-400" />
                {item}
              </li>
            ))}
          </ul>
          <div className="mt-4 border-t border-brand-200/60 pt-3 text-[11.5px] text-slate-500 dark:border-brand-500/20 dark:text-slate-400">
            {t("reports.helperFooter")}
          </div>
        </div>
      </aside>
    </div>
  );
}

// ── Previous reports tab ───────────────────────────────────────────────────────

type StatusFilter = "all" | "PENDING_REVIEW" | "ESCALATED" | "EOF_REPORTED";
type SevFilter = "all" | "MILD" | "MODERATE" | "SEVERE";

interface PreviousReportsProps {
  items: SideEffectReport[] | null;
  loading: boolean;
  usingFallback: boolean;
  fallbackError: string | null;
  busyId: string | null;
  onFlag: (r: SideEffectReport) => void;
  onNotify: (r: SideEffectReport) => void;
  onViewProfile: (r: SideEffectReport) => void;
}

function PreviousReports({
  items,
  loading,
  usingFallback,
  fallbackError,
  busyId,
  onFlag,
  onNotify,
  onViewProfile,
}: PreviousReportsProps) {
  const { t } = useTranslation();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sevFilter, setSevFilter] = useState<SevFilter>("all");

  const statusTabs: { value: StatusFilter; label: string }[] = [
    { value: "all", label: t("reports.filterAll") },
    { value: "PENDING_REVIEW", label: t("reports.filterDraft") },
    { value: "ESCALATED", label: t("reports.filterSubmitted") },
    { value: "EOF_REPORTED", label: t("reports.filterAcknowledged") },
  ];
  const sevTabs: { value: SevFilter; label: string }[] = [
    { value: "all", label: t("reports.filterAll") },
    { value: "MILD", label: t("reports.severityMild") },
    { value: "MODERATE", label: t("reports.severityModerate") },
    { value: "SEVERE", label: t("reports.severitySevere") },
  ];

  const visible = useMemo(
    () =>
      items
        ? items.filter(
            (r) =>
              (statusFilter === "all" || r.status === statusFilter) &&
              (sevFilter === "all" || r.severity === sevFilter),
          )
        : null,
    [items, statusFilter, sevFilter],
  );

  const empty = !loading && (!visible || visible.length === 0);

  return (
    <div>
      {usingFallback && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>
            {t("reports.fallbackWarning")}
            {fallbackError && (
              <span className="ml-1 text-amber-700/80 dark:text-amber-400">({fallbackError})</span>
            )}
          </span>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-800/50">
          {statusTabs.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setStatusFilter(value)}
              className={`rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                statusFilter === value
                  ? "bg-white text-brand-700 shadow-card dark:bg-slate-900 dark:text-brand-300"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-800/50">
          {sevTabs.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setSevFilter(value)}
              className={`rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                sevFilter === value
                  ? "bg-white text-brand-700 shadow-card dark:bg-slate-900 dark:text-brand-300"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-[13px] text-slate-500 shadow-card dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          <span className="spinner text-brand-600" /> Loading reports…
        </div>
      )}

      {empty && (
        <div className="flex animate-fade-in flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-16 text-center shadow-card dark:border-slate-800 dark:bg-slate-900">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
            <FileTextIcon width={22} height={22} />
          </div>
          <h3 className="mt-4 text-[15px] font-bold text-slate-900 dark:text-slate-100">
            {t("reports.noReportsTitle")}
          </h3>
          <p className="mt-1.5 max-w-[320px] text-[13px] text-slate-500 dark:text-slate-400">
            {t("reports.noReportsDesc")}
          </p>
        </div>
      )}

      {!loading && visible && visible.length > 0 && (
        <div className="animate-fade-in overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
          <div className="grid grid-cols-[110px_150px_1fr_110px_130px_120px] items-center gap-4 border-b border-slate-200 bg-slate-50 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-500">
            <span>{t("reports.colDate")}</span>
            <span>{t("reports.colPatient")}</span>
            <span>{t("reports.colMedicine")}</span>
            <span>{t("reports.colSeverity")}</span>
            <span>{t("reports.colStatus")}</span>
            <span />
          </div>
          {visible.map((r, i) => (
            <div
              key={r.id}
              className={`group grid grid-cols-[110px_150px_1fr_110px_130px_120px] items-center gap-4 px-5 py-3.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60 ${
                i > 0 ? "border-t border-slate-100 dark:border-slate-800" : ""
              }`}
            >
              <span className="mono text-[12.5px] text-slate-500 dark:text-slate-400">
                {formatTimestamp(r.reportedAt)}
              </span>
              <span className="mono text-[12.5px] text-slate-700 dark:text-slate-300">
                {r.patientName}
              </span>
              <span className="truncate text-[13px] font-medium text-slate-900 dark:text-slate-100">
                {r.drugName}
              </span>
              <span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${SEV_TONE[r.severity]}`}
                >
                  {SEVERITY_LABEL[r.severity]}
                </span>
              </span>
              <span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${STATUS_TONE[r.status]}`}
                >
                  {STATUS_LABEL[r.status]}
                </span>
              </span>
              <div className="flex items-center justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  type="button"
                  onClick={() => onViewProfile(r)}
                  className="text-[12px] font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400"
                >
                  {t("reports.view")}
                </button>
                {r.status === "PENDING_REVIEW" && (
                  <button
                    type="button"
                    onClick={() => onFlag(r)}
                    disabled={busyId === r.id}
                    className="text-[12px] font-semibold text-slate-500 hover:text-slate-700 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200"
                  >
                    {t("reports.edit")}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onNotify(r)}
                  disabled={busyId === r.id || !r.rxId}
                  className="text-[12px] font-semibold text-slate-400 hover:text-red-600 disabled:opacity-40 dark:text-slate-500 dark:hover:text-red-400"
                >
                  {t("reports.withdraw")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function SideEffects() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();

  const [tab, setTab] = useState<"report" | "previous">("report");
  const query = "";
  const sort: AdrSort = "date";
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
  const [fallbackMaster, setFallbackMaster] = useState<SideEffectReport[]>([...FALLBACK_REPORTS]);
  const [submittedRef, setSubmittedRef] = useState<string | null>(null);

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

  function handleSubmitted(report: SideEffectReport) {
    setItems((cur) => (cur ? [report, ...cur] : [report]));
    setStats((cur) => ({
      ...cur,
      total: cur.total + 1,
      pendingReview: cur.pendingReview + 1,
    }));
    if (usingFallback) {
      setFallbackMaster((cur) => [report, ...cur]);
    }
    setSubmittedRef(report.id);
    setTimeout(() => setTab("previous"), 2000);
  }

  const statCards = useMemo(
    () => [
      {
        label: t("reports.statTotal"),
        value: stats.total,
        Icon: AlertTriangleIcon,
        tone: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
        vc: "text-slate-900 dark:text-slate-100",
      },
      {
        label: t("reports.statPending"),
        value: stats.pendingReview,
        Icon: ClockIcon,
        tone: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
        vc: "text-amber-700 dark:text-amber-400",
      },
      {
        label: t("reports.statSevere"),
        value: stats.severe,
        Icon: AlertOctagonIcon,
        tone: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
        vc: "text-red-700 dark:text-red-400",
      },
      {
        label: t("reports.statEscalated"),
        value: stats.escalated,
        Icon: FlagIcon,
        tone: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
        vc: "text-blue-700 dark:text-blue-400",
      },
    ],
    [stats, t],
  );

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-8 lg:px-8">
      {/* header */}
      <div className="mb-6">
        <h1 className="text-[24px] font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("reports.title")}
        </h1>
        <p className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">
          {t("reports.subtitle")}
        </p>
      </div>

      {/* stat strip */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {statCards.map(({ label, value, Icon, tone, vc }) => (
          <div
            key={label}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[11.5px] font-medium text-slate-500 dark:text-slate-400">
                  {label}
                </div>
                <div className={`mt-0.5 text-[22px] font-bold tabular-nums ${vc}`}>
                  {loading ? "—" : value}
                </div>
              </div>
              <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${tone}`}>
                <Icon width={16} height={16} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* tabs */}
      <div className="mb-6 flex items-center gap-1 border-b border-slate-200 dark:border-slate-800">
        {(["report", "previous"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => {
              if (v === "report") setSubmittedRef(null);
              setTab(v);
            }}
            className={`-mb-px border-b-2 px-4 py-2.5 text-[13.5px] font-semibold transition-colors ${
              tab === v
                ? "border-brand-600 text-brand-700 dark:border-brand-400 dark:text-brand-300"
                : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {t(v === "report" ? "reports.tabReport" : "reports.tabPrevious")}
          </button>
        ))}
      </div>

      {tab === "report" ? (
        <div className="animate-fade-in">
          {!submittedRef && (
            <h2 className="mb-4 text-[16px] font-bold text-slate-900 dark:text-slate-100">
              {t("reports.newReportTitle")}
            </h2>
          )}
          <ReportForm
            key={submittedRef ?? "form"}
            onSubmitted={handleSubmitted}
            submittedRef={submittedRef}
          />
        </div>
      ) : (
        <PreviousReports
          items={items}
          loading={loading}
          usingFallback={usingFallback}
          fallbackError={fallbackError}
          busyId={busyId}
          onFlag={onFlag}
          onNotify={onNotifyPhysician}
          onViewProfile={(r) => {
            if (r.patientId) navigate(`/patients/${r.patientId}`);
            else toast("Patient ID not available for this report.", "warn");
          }}
        />
      )}
    </div>
  );
}
