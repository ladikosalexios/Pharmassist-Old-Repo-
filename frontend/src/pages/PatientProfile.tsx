import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertCircleIcon, AlertTriangleIcon, AlertOctagonIcon, CheckCircleIcon,
  ChevronLeftIcon, ChevronRightIcon, PhoneIcon, ShieldIcon, UsersIcon,
} from "../components/Icons";
import {
  ApiError, getPatient, getPatientPrescriptions, getPatientSideEffects,
} from "../lib/api";
import type {
  AdrSeverity, AdrStatus, OrganFunction, PatientProfile as Profile,
  PatientRxHistoryRow, PatientSafetyFlags, SideEffectReport,
} from "../types";

const TABS = ["rx", "adr", "safety"] as const;
type Tab = typeof TABS[number];
const TAB_LABEL: Record<Tab, string> = {
  rx:     "Prescription History",
  adr:    "Side Effect History",
  safety: "Safety Profile",
};

const RX_STATUS_CHIP: Record<string, string> = {
  PENDING:   "bg-amber-100 text-amber-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  FLAGGED:   "bg-red-100 text-red-800",
};
const RX_STATUS_LABEL: Record<string, string> = {
  PENDING:   "Pending",
  COMPLETED: "Completed",
  FLAGGED:   "Flagged",
};

const SEVERITY_TONE: Record<AdrSeverity, string> = {
  MILD:     "bg-amber-100 text-amber-800",
  MODERATE: "bg-orange-100 text-orange-800",
  SEVERE:   "bg-red-100 text-red-800",
};
const SEVERITY_LABEL: Record<AdrSeverity, string> = {
  MILD: "Mild", MODERATE: "Moderate", SEVERE: "Severe",
};
const ADR_STATUS_TONE: Record<AdrStatus, string> = {
  PENDING_REVIEW: "border border-amber-300 bg-white text-amber-800",
  ESCALATED:      "border border-red-300 bg-white text-red-800",
  EOF_REPORTED:   "border border-emerald-600 bg-emerald-600 text-white",
};
const ADR_STATUS_LABEL: Record<AdrStatus, string> = {
  PENDING_REVIEW: "Pending Review",
  ESCALATED:      "Escalated",
  EOF_REPORTED:   "EOF Reported",
};

export function PatientProfile() {
  const { id = "" } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const fromRx = search.get("from");
  const navigate = useNavigate();

  const [tab, setTab] = useState<Tab>("rx");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  const [rxHistory, setRxHistory] = useState<PatientRxHistoryRow[] | null>(null);
  const [rxError, setRxError] = useState<string | null>(null);

  const [adrHistory, setAdrHistory] = useState<SideEffectReport[] | null>(null);
  const [adrError, setAdrError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setProfileLoading(true);
    setProfileError(null);
    setProfile(null);
    setRxHistory(null);
    setAdrHistory(null);

    getPatient(id)
      .then((data) => { if (active) setProfile(data); })
      .catch((e: unknown) => {
        if (!active) return;
        setProfileError(e instanceof ApiError ? e.message : "Could not load patient profile.");
      })
      .finally(() => { if (active) setProfileLoading(false); });

    getPatientPrescriptions(id)
      .then((items) => { if (active) setRxHistory(items); })
      .catch((e: unknown) => {
        if (!active) return;
        setRxError(e instanceof ApiError ? e.message : "Could not load prescription history.");
      });

    getPatientSideEffects(id)
      .then((items) => { if (active) setAdrHistory(items); })
      .catch((e: unknown) => {
        if (!active) return;
        setAdrError(e instanceof ApiError ? e.message : "Could not load side-effect history.");
      });

    return () => { active = false; };
  }, [id]);

  const isPregnant =
    profile?.safetyFlags?.pregnancyWeeks != null && profile.safetyFlags.pregnancyWeeks > 0;

  return (
    <div className="p-8">
      {/* Back link */}
      <div className="mb-3 flex items-center gap-2 text-sm">
        {fromRx ? (
          <Link to={`/prescription/${fromRx}`} className="inline-flex items-center gap-1 text-brand-600 hover:underline">
            <ChevronLeftIcon width={14} height={14} /> Back to {fromRx}
          </Link>
        ) : (
          <button type="button" onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-brand-600 hover:underline">
            <ChevronLeftIcon width={14} height={14} /> Back
          </button>
        )}
      </div>

      {/* Profile header */}
      {profileLoading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-brand-600" /> Loading profile…
        </div>
      ) : profileError || !profile ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{profileError ?? "Patient profile not available."}</span>
        </div>
      ) : (
        <>
          <header className="card p-6">
            <div className="flex flex-wrap items-start gap-6">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-brand-100 text-brand-700">
                <UsersIcon width={24} height={24} />
              </div>
              <div className="min-w-0 flex-1">
                <h1 className="text-2xl font-bold text-slate-900">{profile.name}</h1>
                <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                  {profile.amka && <span>AMKA: <span className="font-mono text-slate-800">{profile.amka}</span></span>}
                  {typeof profile.age === "number" && <span>{profile.age} years</span>}
                  {profile.dateOfBirth && <span>DOB: {profile.dateOfBirth}</span>}
                  {profile.sex && <span>Sex: {profile.sex === "F" ? "Female" : profile.sex === "M" ? "Male" : profile.sex}</span>}
                  {profile.phone && (
                    <a href={`tel:${profile.phone}`} className="inline-flex items-center gap-1 text-brand-600 hover:underline">
                      <PhoneIcon width={13} height={13} /> {profile.phone}
                    </a>
                  )}
                </div>

                <div className="mt-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Medical Conditions</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profile.conditions && profile.conditions.length > 0 ? (
                      profile.conditions.map((c) => (
                        <span key={c} className="chip border border-brand-100 bg-brand-50 text-brand-700">{c}</span>
                      ))
                    ) : (
                      <span className="text-sm text-slate-500">None recorded.</span>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Allergies</div>
                  <div className="mt-2">
                    {profile.allergies && profile.allergies.length > 0 ? (
                      <ul className="flex flex-wrap gap-2">
                        {profile.allergies.map((a) => (
                          <li key={a} className="chip border border-red-200 bg-red-50 text-red-800">{a}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-sm text-slate-500">No known allergies.</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="shrink-0">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] text-slate-500">
                  Read-only — edits are made by the prescribing physician.
                </div>
              </div>
            </div>
          </header>

          {/* Tabs */}
          <div role="tablist" aria-label="Patient sections" className="mt-6 mb-4 flex gap-1 border-b border-slate-200">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                type="button"
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                  tab === t
                    ? "border-brand-600 text-brand-700"
                    : "border-transparent text-slate-600 hover:text-slate-900"
                }`}
              >
                {TAB_LABEL[t]}
              </button>
            ))}
          </div>

          {tab === "rx"     && <RxHistoryTab rows={rxHistory} error={rxError} />}
          {tab === "adr"    && <AdrHistoryTab rows={adrHistory} error={adrError} />}
          {tab === "safety" && (
            <SafetyProfileTab
              flags={profile.safetyFlags}
              intolerances={profile.intolerances ?? []}
              isPregnant={isPregnant}
            />
          )}
        </>
      )}
    </div>
  );
}

function RxHistoryTab({ rows, error }: { rows: PatientRxHistoryRow[] | null; error: string | null }) {
  if (error) {
    return (
      <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
        <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }
  if (!rows) {
    return (
      <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
        <span className="spinner text-brand-600" /> Loading prescription history…
      </div>
    );
  }
  if (rows.length === 0) {
    return <div className="card px-4 py-10 text-center text-sm text-slate-500">No prescriptions on record.</div>;
  }
  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5">Date</th>
              <th className="px-4 py-2.5">Drug</th>
              <th className="px-4 py-2.5">Prescriber</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr
                key={r.rxId}
                tabIndex={0}
                onClick={() => (window.location.href = `/prescription/${r.rxId}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") window.location.href = `/prescription/${r.rxId}`;
                }}
                className="cursor-pointer hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
              >
                <td className="px-4 py-3 text-slate-700">{r.date}</td>
                <td className="px-4 py-3">
                  <Link to={`/prescription/${r.rxId}`} className="text-brand-600 hover:underline" onClick={(e) => e.stopPropagation()}>
                    {r.drugName}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-700">{r.prescriberName}</td>
                <td className="px-4 py-3">
                  <span className={`chip ${RX_STATUS_CHIP[r.status] ?? "bg-slate-100 text-slate-800"}`}>
                    {RX_STATUS_LABEL[r.status] ?? r.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-slate-400">
                  <ChevronRightIcon width={14} height={14} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AdrHistoryTab({ rows, error }: { rows: SideEffectReport[] | null; error: string | null }) {
  if (error) {
    return (
      <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
        <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }
  if (!rows) {
    return (
      <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
        <span className="spinner text-brand-600" /> Loading side-effect history…
      </div>
    );
  }
  if (rows.length === 0) {
    return <div className="card px-4 py-10 text-center text-sm text-slate-500">No adverse drug reactions on record.</div>;
  }
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.id}>
          <article className="card p-4">
            <div className="flex flex-wrap items-center gap-2">
              {r.rxId ? (
                <Link to={`/prescription/${r.rxId}`} className="text-sm font-semibold text-brand-600 hover:underline">
                  {r.drugName}
                </Link>
              ) : (
                <span className="text-sm font-semibold text-slate-900">{r.drugName}</span>
              )}
              <span className={`chip ${SEVERITY_TONE[r.severity]}`}>{SEVERITY_LABEL[r.severity]}</span>
              <span className={`chip ${ADR_STATUS_TONE[r.status]}`}>{ADR_STATUS_LABEL[r.status]}</span>
              <span className="ml-auto text-xs text-slate-500">{formatDate(r.reportedAt)}</span>
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-700">{r.symptom}</p>
            <p className="mt-1 text-[12px] text-slate-500">Onset: {r.onset}</p>
          </article>
        </li>
      ))}
    </ul>
  );
}

interface SafetyProfileTabProps {
  flags: PatientSafetyFlags | undefined;
  intolerances: string[];
  isPregnant: boolean;
}

const ORGAN_TONE: Record<OrganFunction, { chip: string; alert: boolean }> = {
  NORMAL:               { chip: "bg-emerald-100 text-emerald-800", alert: false },
  MILD_IMPAIRMENT:      { chip: "bg-amber-100 text-amber-800",     alert: false },
  MODERATE_IMPAIRMENT:  { chip: "bg-red-100 text-red-800",         alert: true },
  SEVERE_IMPAIRMENT:    { chip: "bg-red-100 text-red-800",         alert: true },
};
const ORGAN_LABEL: Record<OrganFunction, string> = {
  NORMAL:               "Normal",
  MILD_IMPAIRMENT:      "Mild impairment",
  MODERATE_IMPAIRMENT:  "Moderate impairment",
  SEVERE_IMPAIRMENT:    "Severe impairment",
};

function SafetyProfileTab({ flags, intolerances, isPregnant }: SafetyProfileTabProps) {
  if (!flags) {
    return <div className="card px-4 py-10 text-center text-sm text-slate-500">No safety profile recorded.</div>;
  }

  const renalTone = ORGAN_TONE[flags.renalFunction];
  const hepaticTone = ORGAN_TONE[flags.hepaticFunction];
  const alerts: string[] = [];
  if (flags.g6pd) alerts.push("G6PD deficiency");
  if (isPregnant) alerts.push(`Pregnancy (${flags.pregnancyWeeks} weeks)`);
  if (renalTone.alert)   alerts.push(`Renal: ${ORGAN_LABEL[flags.renalFunction]}`);
  if (hepaticTone.alert) alerts.push(`Hepatic: ${ORGAN_LABEL[flags.hepaticFunction]}`);

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <h2 className="mb-3 text-base font-semibold text-slate-900">Drug Intolerances</h2>
        {intolerances.length === 0 ? (
          <p className="text-sm text-slate-500">None recorded.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {intolerances.map((i) => (
              <li key={i} className="chip border border-amber-200 bg-amber-50 text-amber-800">{i}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">Special Flags</h2>
          {alerts.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
              <AlertOctagonIcon width={12} height={12} /> {alerts.length} alert{alerts.length === 1 ? "" : "s"} active
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FlagCard
            icon={<ShieldIcon width={16} height={16} />}
            label="G6PD Deficiency"
            tone={flags.g6pd ? "alert" : "normal"}
            value={flags.g6pd ? "Positive — review oxidative-stress drugs" : "Negative"}
          />
          <FlagCard
            icon={<AlertTriangleIcon width={16} height={16} />}
            label="Pregnancy"
            tone={isPregnant ? "warn" : "normal"}
            value={isPregnant ? `${flags.pregnancyWeeks} weeks — verify teratogenicity` : "Not pregnant / not applicable"}
          />
          <FlagCard
            icon={<ShieldIcon width={16} height={16} />}
            label="Renal Function"
            tone={flags.renalFunction === "NORMAL" ? "normal" : flags.renalFunction === "MILD_IMPAIRMENT" ? "warn" : "alert"}
            value={ORGAN_LABEL[flags.renalFunction]}
          />
          <FlagCard
            icon={<ShieldIcon width={16} height={16} />}
            label="Hepatic Function"
            tone={flags.hepaticFunction === "NORMAL" ? "normal" : flags.hepaticFunction === "MILD_IMPAIRMENT" ? "warn" : "alert"}
            value={ORGAN_LABEL[flags.hepaticFunction]}
          />
        </div>

        <p className="mt-3 text-[12px] text-slate-500">
          These flags surface during automated safety checks on every prescription.
        </p>
      </section>
    </div>
  );
}

type FlagTone = "normal" | "warn" | "alert";
const FLAG_TONE: Record<FlagTone, { box: string; label: string; icon: React.ReactNode }> = {
  normal: { box: "border-emerald-200 bg-emerald-50 text-emerald-800", label: "text-emerald-700", icon: <CheckCircleIcon width={14} height={14} /> },
  warn:   { box: "border-amber-200 bg-amber-50 text-amber-800",       label: "text-amber-700",   icon: <AlertTriangleIcon width={14} height={14} /> },
  alert:  { box: "border-red-200 bg-red-50 text-red-800",             label: "text-red-700",     icon: <AlertOctagonIcon width={14} height={14} /> },
};

function FlagCard({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: FlagTone }) {
  const t = FLAG_TONE[tone];
  return (
    <div className={`rounded-xl border p-3.5 ${t.box}`}>
      <div className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide ${t.label}`}>
        {icon}
        <span>{label}</span>
        <span className="ml-auto">{t.icon}</span>
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-slate-800">{value}</p>
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
