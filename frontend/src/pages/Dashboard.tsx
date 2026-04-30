import { Link } from "react-router-dom";
import { ClockIcon, FlagIcon, CheckIcon, AlertCircleIcon, ChevronRightIcon, AlertTriangleIcon, ShieldIcon } from "../components/Icons";
import type { QueueItem } from "../types";

const STATS = [
  { label: "Pending Verification", value: 3, Icon: ClockIcon,      tone: "bg-amber-100 text-amber-700" },
  { label: "Flagged Issues",        value: 1, Icon: FlagIcon,       tone: "bg-red-100 text-red-700" },
  { label: "Completed Today",       value: 1, Icon: CheckIcon,      tone: "bg-emerald-100 text-emerald-700" },
  { label: "Critical Alerts",       value: 1, Icon: AlertCircleIcon, tone: "bg-red-100 text-red-700" },
];

const QUEUE: QueueItem[] = [
  { rxId: "RX2024-001", patientName: "Sarah Johnson", medication: "Amoxicillin", physician: "Dr. Michael Chen", date: "2026-03-11", status: "PENDING" },
  { rxId: "RX2024-002", patientName: "James Martinez", medication: "Warfarin",   physician: "Dr. Emily Roberts", date: "2026-03-11", status: "FLAGGED" },
  { rxId: "RX2024-003", patientName: "Maria Garcia",   medication: "Lisinopril", physician: "Dr. David Lee",     date: "2026-03-11", status: "PENDING" },
  { rxId: "RX2024-005", patientName: "Maria Stavrou",  medication: "Warfarin",   physician: "Dr. Michael Chen",  date: "2026-04-28", status: "PENDING" },
];

const ALERTS: { kind: "INTERACTION" | "G6PD" | "PREGNANCY"; title: string; body: string; rxId?: string }[] = [
  { kind: "INTERACTION", title: "INTERACTION", body: "Warfarin + Aspirin: High risk of bleeding. Immediate review required.", rxId: "RX2024-005" },
  { kind: "G6PD",        title: "G6PD",        body: "Patient P003 has G6PD deficiency. Verify medication safety." },
  { kind: "PREGNANCY",   title: "PREGNANCY",   body: "Patient P001 is 18 weeks pregnant. Check teratogenicity." },
];

const STATUS_CHIP: Record<QueueItem["status"], string> = {
  PENDING:  "bg-amber-100 text-amber-800",
  FLAGGED:  "bg-red-100 text-red-800",
  APPROVED: "bg-emerald-100 text-emerald-800",
};

const ALERT_TONE: Record<typeof ALERTS[number]["kind"], { box: string; label: string }> = {
  INTERACTION: { box: "border-red-200 bg-red-50",       label: "text-red-700" },
  G6PD:        { box: "border-amber-200 bg-amber-50",   label: "text-amber-700" },
  PREGNANCY:   { box: "border-yellow-200 bg-yellow-50", label: "text-yellow-700" },
};

export function Dashboard() {
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  return (
    <div className="p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-bold text-slate-900">Pharmacist Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">{today}</p>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STATS.map(({ label, value, Icon, tone }) => (
          <div key={label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-medium text-slate-500">{label}</div>
                <div className="mt-1 text-3xl font-bold text-slate-900">{value}</div>
              </div>
              <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone}`}>
                <Icon width={18} height={18} />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="border-b border-slate-200 px-6 py-4">
            <h2 className="text-base font-semibold text-slate-900">Prescription Queue</h2>
          </div>
          <ul>
            {QUEUE.map((rx) => (
              <li key={rx.rxId}>
                <Link
                  to={`/prescription/${rx.rxId}`}
                  className="flex items-center justify-between gap-4 border-b border-slate-100 px-6 py-4 last:border-b-0 hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900">{rx.patientName}</span>
                      <span className={`chip ${STATUS_CHIP[rx.status]}`}>
                        {rx.status === "PENDING" ? "Pending" : rx.status === "FLAGGED" ? "Flagged" : "Approved"}
                      </span>
                    </div>
                    <div className="mt-1 grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-slate-500 sm:grid-cols-2">
                      <span>Code: <span className="font-medium text-slate-700">{rx.rxId}</span></span>
                      <span>Physician: <span className="font-medium text-slate-700">{rx.physician}</span></span>
                      <span>Medication: <span className="font-medium text-slate-700">{rx.medication}</span></span>
                      <span>Date: <span className="font-medium text-slate-700">{rx.date}</span></span>
                    </div>
                  </div>
                  <ChevronRightIcon className="shrink-0 text-slate-400" />
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <aside className="card self-start">
          <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <AlertCircleIcon width={16} height={16} className="text-red-600" />
            <h2 className="text-base font-semibold text-slate-900">Safety Alerts</h2>
          </div>
          <div className="space-y-3 p-4">
            {ALERTS.map((a, i) => {
              const tone = ALERT_TONE[a.kind];
              return (
                <div key={i} className={`rounded-xl border p-3.5 ${tone.box}`}>
                  <div className="flex items-center gap-1.5">
                    {a.kind === "INTERACTION" ? (
                      <ShieldIcon width={14} height={14} className={tone.label} />
                    ) : a.kind === "G6PD" ? (
                      <ShieldIcon width={14} height={14} className={tone.label} />
                    ) : (
                      <AlertTriangleIcon width={14} height={14} className={tone.label} />
                    )}
                    <span className={`text-xs font-bold tracking-wide ${tone.label}`}>{a.title}</span>
                  </div>
                  <p className="mt-1.5 text-[13px] text-slate-700">{a.body}</p>
                  {a.rxId && (
                    <Link to={`/prescription/${a.rxId}`} className="mt-2 inline-flex items-center gap-1 text-[12px] font-semibold text-brand-600 hover:underline">
                      View Prescription <ChevronRightIcon width={12} height={12} />
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}
