import { Link } from "react-router-dom";
import { ClockIcon, FlagIcon, CheckIcon, AlertCircleIcon, ChevronRightIcon } from "../components/Icons";
import { SafetyAlertsPanel } from "../components/SafetyAlertsPanel";
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

const STATUS_CHIP: Record<QueueItem["status"], string> = {
  PENDING:  "bg-amber-100 text-amber-800",
  FLAGGED:  "bg-red-100 text-red-800",
  APPROVED: "bg-emerald-100 text-emerald-800",
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

        <div className="self-start">
          <SafetyAlertsPanel />
        </div>
      </div>
    </div>
  );
}
