import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ClockIcon,
  FlagIcon,
  CheckIcon,
  AlertCircleIcon,
  ChevronRightIcon,
  FileTextIcon,
} from "../components/Icons";
import { SafetyAlertsPanel } from "../components/SafetyAlertsPanel";
import { KeyboardShortcutsCard } from "../components/KeyboardShortcutsCard";
import { ApiError, getActiveAlerts, listPrescriptions } from "../lib/api";
import type { ActiveAlert, QueueItem } from "../types";

const STATUS_CHIP: Record<QueueItem["status"], string> = {
  PENDING: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-400",
  FLAGGED: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-400",
  COMPLETED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-400",
};

const STATUS_LABEL_KEY: Record<QueueItem["status"], string> = {
  PENDING: "dashboard.statusPending",
  FLAGGED: "dashboard.statusFlagged",
  COMPLETED: "dashboard.statusCompleted",
};

export function Dashboard() {
  const { t, i18n } = useTranslation();
  const today = new Date().toLocaleDateString(i18n.language?.startsWith("en") ? "en-GB" : "el-GR", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<ActiveAlert[] | null>(null);

  useEffect(() => {
    let active = true;
    listPrescriptions()
      .then((items) => {
        if (active) setQueue(items);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setQueueError(e instanceof ApiError ? e.message : t("dashboard.queueLoadError"));
      });
    // Critical Alerts mirrors the block-severity count in SafetyAlertsPanel.
    // Both fetch /alerts/active independently for now — fine until a shared
    // store lands; the call is cached server-side and cheap.
    getActiveAlerts()
      .then((data) => {
        if (active) setAlerts(data);
      })
      .catch(() => {
        /* SafetyAlertsPanel surfaces the error; the stat just stays at — */
      });
    return () => {
      active = false;
    };
  }, [t]);

  const counts = useMemo(() => {
    const c = { PENDING: 0, FLAGGED: 0, COMPLETED: 0 };
    for (const q of queue ?? []) c[q.status]++;
    return c;
  }, [queue]);

  const criticalCount = useMemo(
    () => (alerts ?? []).filter((a) => a.status === "block").length,
    [alerts],
  );

  const stats = [
    {
      label: t("dashboard.pendingVerification"),
      value: counts.PENDING,
      ready: queue !== null,
      Icon: ClockIcon,
      tone: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
    },
    {
      label: t("dashboard.flaggedIssues"),
      value: counts.FLAGGED,
      ready: queue !== null,
      Icon: FlagIcon,
      tone: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
    },
    {
      label: t("dashboard.completed"),
      value: counts.COMPLETED,
      ready: queue !== null,
      Icon: CheckIcon,
      tone: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
    },
    {
      label: t("dashboard.criticalAlerts"),
      value: criticalCount,
      ready: alerts !== null,
      Icon: AlertCircleIcon,
      tone: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
    },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          {t("dashboard.title")}
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{today}</p>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(({ label, value, ready, Icon, tone }) => (
          <div key={label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-medium text-slate-500 dark:text-slate-400">
                  {label}
                </div>
                <div className="mt-1 text-3xl font-bold text-slate-900 dark:text-slate-100">
                  {ready ? value : "—"}
                </div>
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
          <div className="border-b border-slate-200 px-6 py-4 dark:border-slate-800">
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {t("dashboard.prescriptionQueue")}
            </h2>
          </div>
          {queueError ? (
            <div className="m-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{queueError}</span>
            </div>
          ) : !queue ? (
            <div className="px-6 py-8 text-sm text-slate-500 dark:text-slate-400">
              <span className="spinner text-brand-600" /> {t("dashboard.loadingQueue")}
            </div>
          ) : queue.length === 0 ? (
            <div className="px-6 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
              {t("dashboard.queueEmpty")}
            </div>
          ) : (
            <ul>
              {queue.map((rx) => (
                <li key={rx.rxId}>
                  <Link
                    to={`/prescription/${rx.rxId}`}
                    className="flex items-center justify-between gap-4 border-b border-slate-100 px-6 py-4 last:border-b-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                          {rx.patientName}
                        </span>
                        <span className={`chip ${STATUS_CHIP[rx.status]}`}>
                          {t(STATUS_LABEL_KEY[rx.status])}
                        </span>
                      </div>
                      <div className="mt-1 grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-slate-500 dark:text-slate-400 sm:grid-cols-2">
                        <span>
                          {t("dashboard.code")}:{" "}
                          <span className="font-medium text-slate-700 dark:text-slate-300">
                            {rx.rxId}
                          </span>
                        </span>
                        <span>
                          {t("dashboard.physician")}:{" "}
                          <span className="font-medium text-slate-700 dark:text-slate-300">
                            {rx.physician}
                          </span>
                        </span>
                        <span>
                          {t("dashboard.medication")}:{" "}
                          <span className="font-medium text-slate-700 dark:text-slate-300">
                            {rx.medication}
                          </span>
                        </span>
                        <span>
                          {t("dashboard.date")}:{" "}
                          <span className="font-medium text-slate-700 dark:text-slate-300">
                            {rx.date}
                          </span>
                        </span>
                      </div>
                    </div>
                    <ChevronRightIcon className="shrink-0 text-slate-400 dark:text-slate-500" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="self-start space-y-6">
          <section className="card p-5">
            <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">
              {t("dashboard.quickActions")}
            </h2>
            <Link to="/instructions" className="btn btn-primary w-full justify-center">
              <FileTextIcon /> {t("dashboard.generateInstructions")}
            </Link>
            <p className="mt-2 text-[12px] text-slate-500 dark:text-slate-400">
              {t("dashboard.generateInstructionsDesc")}
            </p>
          </section>
          <SafetyAlertsPanel />
          <KeyboardShortcutsCard />
        </div>
      </div>
    </div>
  );
}
