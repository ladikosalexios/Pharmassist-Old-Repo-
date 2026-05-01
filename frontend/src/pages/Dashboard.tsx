import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ClockIcon, FlagIcon, CheckIcon, AlertCircleIcon, ChevronRightIcon, FileTextIcon } from "../components/Icons";
import { SafetyAlertsPanel } from "../components/SafetyAlertsPanel";
import { KeyboardShortcutsCard } from "../components/KeyboardShortcutsCard";
import { ApiError, listPrescriptions } from "../lib/api";
import type { QueueItem } from "../types";

const STATUS_CHIP: Record<QueueItem["status"], string> = {
  PENDING:   "bg-amber-100 text-amber-800",
  FLAGGED:   "bg-red-100 text-red-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
};

const STATUS_LABEL: Record<QueueItem["status"], string> = {
  PENDING:   "Pending",
  FLAGGED:   "Flagged",
  COMPLETED: "Completed",
};

export function Dashboard() {
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listPrescriptions()
      .then((items) => { if (active) setQueue(items); })
      .catch((e: unknown) => {
        if (!active) return;
        setQueueError(e instanceof ApiError ? e.message : "Could not load the prescription queue.");
      });
    return () => { active = false; };
  }, []);

  const counts = useMemo(() => {
    const c = { PENDING: 0, FLAGGED: 0, COMPLETED: 0 };
    for (const q of queue ?? []) c[q.status]++;
    return c;
  }, [queue]);

  const stats = [
    { label: "Pending Verification", value: counts.PENDING,   Icon: ClockIcon,       tone: "bg-amber-100 text-amber-700" },
    { label: "Flagged Issues",       value: counts.FLAGGED,   Icon: FlagIcon,        tone: "bg-red-100 text-red-700" },
    { label: "Completed Today",      value: counts.COMPLETED, Icon: CheckIcon,       tone: "bg-emerald-100 text-emerald-700" },
    // Critical Alerts is sourced from /alerts/active in SafetyAlertsPanel; we keep
    // a placeholder here until we lift that into a shared store.
    { label: "Critical Alerts",      value: 1,                Icon: AlertCircleIcon, tone: "bg-red-100 text-red-700" },
  ];

  return (
    <div className="p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-bold text-slate-900">Pharmacist Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">{today}</p>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(({ label, value, Icon, tone }) => (
          <div key={label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-medium text-slate-500">{label}</div>
                <div className="mt-1 text-3xl font-bold text-slate-900">{queue || label === "Critical Alerts" ? value : "—"}</div>
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
          {queueError ? (
            <div className="m-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{queueError}</span>
            </div>
          ) : !queue ? (
            <div className="px-6 py-8 text-sm text-slate-500"><span className="spinner text-brand-600" /> Loading queue…</div>
          ) : queue.length === 0 ? (
            <div className="px-6 py-8 text-center text-sm text-slate-500">No prescriptions in the queue.</div>
          ) : (
            <ul>
              {queue.map((rx) => (
                <li key={rx.rxId}>
                  <Link
                    to={`/prescription/${rx.rxId}`}
                    className="flex items-center justify-between gap-4 border-b border-slate-100 px-6 py-4 last:border-b-0 hover:bg-slate-50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-900">{rx.patientName}</span>
                        <span className={`chip ${STATUS_CHIP[rx.status]}`}>{STATUS_LABEL[rx.status]}</span>
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
          )}
        </div>

        <div className="self-start space-y-6">
          <section className="card p-5">
            <h2 className="mb-3 text-base font-semibold text-slate-900">Quick Actions</h2>
            <Link to="/instructions" className="btn btn-primary w-full justify-center">
              <FileTextIcon /> Generate Instructions
            </Link>
            <p className="mt-2 text-[12px] text-slate-500">
              Compose patient counselling notes for an approved prescription.
            </p>
          </section>
          <SafetyAlertsPanel />
          <KeyboardShortcutsCard />
        </div>
      </div>
    </div>
  );
}
