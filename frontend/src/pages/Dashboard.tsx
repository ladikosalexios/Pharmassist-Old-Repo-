import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import {
  BarcodeIcon,
  KeyIcon,
  ShieldIcon,
  ChevronRightIcon,
  CheckIcon,
  CheckCircleIcon,
  FlagIcon,
  AlertCircleIcon,
  AlertTriangleIcon,
} from "../components/Icons";
import { SafetyAlertsPanel } from "../components/SafetyAlertsPanel";
import { useAuth } from "../lib/auth";
import { useToast } from "../components/Toast";
import { ApiError, getActiveAlerts, listPrescriptions } from "../lib/api";
import type { ActiveAlert, QueueItem } from "../types";

// Platform-aware shortcut hint (⌘K on Apple, Ctrl+K elsewhere). Computed once;
// `navigator` is always present in the browser, guarded for SSR/tests.
const IS_APPLE =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || "");

interface AlertMeta {
  count: number;
  hasBlock: boolean;
}

export function Dashboard() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const scannerRef = useRef<HTMLInputElement>(null);

  const today = new Date().toLocaleDateString(i18n.language?.startsWith("en") ? "en-GB" : "el-GR", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<ActiveAlert[]>([]);

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
    // The in-progress rows show per-prescription alert chips; the right rail's
    // SafetyAlertsPanel fetches /alerts/active independently (cached server-side).
    getActiveAlerts()
      .then((data) => {
        if (active) setAlerts(data);
      })
      .catch(() => {
        /* the SafetyAlertsPanel surfaces the rail error; chips just stay neutral */
      });
    return () => {
      active = false;
    };
  }, [t]);

  // rxId -> { count, hasBlock } so each in-progress row can show its alert chip
  // and a critical accent without a second fetch.
  const alertsByRx = useMemo(() => {
    const m = new Map<string, AlertMeta>();
    for (const a of alerts) {
      if (!a.rxId) continue;
      const cur = m.get(a.rxId) ?? { count: 0, hasBlock: false };
      cur.count += 1;
      if (a.status === "block") cur.hasBlock = true;
      m.set(a.rxId, cur);
    }
    return m;
  }, [alerts]);

  // "In progress" = the active verification worklist (not yet dispensed);
  // "Today" = prescriptions already completed. Both come from /prescriptions.
  const inProgress = useMemo(
    () => (queue ?? []).filter((q) => q.status === "PENDING" || q.status === "FLAGGED"),
    [queue],
  );
  const todayDone = useMemo(() => (queue ?? []).filter((q) => q.status === "COMPLETED"), [queue]);

  const onScan = (value: string) => {
    const v = value.trim();
    if (!v) return;
    toast(t("dashboard.openingPrescription", { code: v }), "info");
    navigate(`/prescription/${encodeURIComponent(v)}`);
  };

  // ⌘K / Ctrl+K focuses the scanner input.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        scannerRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <SessionStrip />

      <div className="mx-auto w-full max-w-[1100px] px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {t("dashboard.title")}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {today}
            {user?.pharmacy ? (
              <>
                {" · "}
                <span className="font-medium text-slate-600 dark:text-slate-300">
                  {user.pharmacy}
                </span>
              </>
            ) : null}
          </p>
        </header>

        <ScanHero
          scannerRef={scannerRef}
          onScan={onScan}
          onPaperless={() => toast(t("dashboard.paperlessSoon"), "info")}
        />

        <div className="mt-7 grid grid-cols-1 gap-7 lg:grid-cols-[1fr_320px]">
          <div className="space-y-7">
            {queueError ? (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
                <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
                <span>{queueError}</span>
              </div>
            ) : queue === null ? (
              <div className="flex items-center gap-2 px-1 py-6 text-sm text-slate-500 dark:text-slate-400">
                <span className="spinner text-brand-600" /> {t("dashboard.loadingQueue")}
              </div>
            ) : (
              <>
                <InProgressList items={inProgress} alertsByRx={alertsByRx} />
                <TodayList items={todayDone} />
              </>
            )}
          </div>

          <div>
            <SafetyAlertsPanel title={t("dashboard.safetyTitle")} />
          </div>
        </div>

        <div className="mt-8 flex items-center justify-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
          <kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-500 shadow-card dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
            {IS_APPLE ? "⌘K" : "Ctrl+K"}
          </kbd>
          {t("dashboard.scanHint")}
        </div>
      </div>
    </div>
  );
}

/* ── ΗΔΥΚΑ session status strip ── */
function SessionStrip() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 sm:px-6 lg:px-8">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
      </span>
      {t("dashboard.sessionActive")}
    </div>
  );
}

/* ── "Start a dispense" scanner hero ── */
function ScanHero({
  scannerRef,
  onScan,
  onPaperless,
}: {
  scannerRef: React.RefObject<HTMLInputElement>;
  onScan: (value: string) => void;
  onPaperless: () => void;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"barcode" | "paperless">("barcode");
  const [barcode, setBarcode] = useState("");
  const [amka, setAmka] = useState("");
  const [pin, setPin] = useState("");

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-cardLg dark:border-slate-800 dark:bg-slate-900 sm:p-7">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[17px] font-bold text-slate-900 dark:text-slate-100">
            {t("dashboard.scanTitle")}
          </h2>
          <p className="mt-0.5 text-[13px] text-slate-500 dark:text-slate-400">
            {t("dashboard.scanSubtitle")}
          </p>
        </div>
        <div className="flex items-center gap-1 self-start rounded-full border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800">
          <button
            type="button"
            onClick={() => setTab("barcode")}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors ${
              tab === "barcode"
                ? "bg-white text-brand-700 shadow-card dark:bg-slate-700 dark:text-brand-300"
                : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            <BarcodeIcon width={15} height={15} /> {t("dashboard.tabBarcode")}
          </button>
          <button
            type="button"
            onClick={() => setTab("paperless")}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors ${
              tab === "paperless"
                ? "bg-white text-brand-700 shadow-card dark:bg-slate-700 dark:text-brand-300"
                : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            <KeyIcon width={15} height={15} /> {t("dashboard.tabPaperless")}
          </button>
        </div>
      </div>

      <div className="rounded-xl bg-brand-50 p-5 dark:bg-brand-500/10 sm:p-6">
        {tab === "barcode" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onScan(barcode);
            }}
          >
            <div className="mb-3 flex items-center gap-2.5 text-brand-700 dark:text-brand-300">
              <BarcodeIcon width={22} height={22} />
              <span className="text-[14px] font-semibold">{t("dashboard.barcodePrompt")}</span>
            </div>
            <div className="flex flex-col gap-2.5 sm:flex-row">
              <input
                ref={scannerRef}
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                autoFocus
                inputMode="numeric"
                aria-label={t("dashboard.barcodePrompt")}
                placeholder={t("dashboard.barcodePlaceholder")}
                className="mono flex-1 rounded-lg border border-brand-200 bg-white px-4 py-3 text-[16px] tracking-wide text-slate-900 outline-none transition-shadow placeholder:font-sans placeholder:tracking-normal placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-brand-500/30 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:ring-brand-500/20"
              />
              <button
                type="submit"
                className="shrink-0 rounded-lg bg-brand-600 px-7 py-3 text-[14px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 dark:hover:bg-brand-500"
              >
                {t("dashboard.open")}
              </button>
            </div>
          </form>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onPaperless();
            }}
          >
            <div className="mb-3 flex items-center gap-2.5 text-brand-700 dark:text-brand-300">
              <ShieldIcon width={22} height={22} />
              <span className="text-[14px] font-semibold">{t("dashboard.paperlessPrompt")}</span>
            </div>
            <div className="flex flex-col gap-2.5 sm:flex-row">
              <input
                value={amka}
                onChange={(e) => setAmka(e.target.value)}
                inputMode="numeric"
                maxLength={11}
                aria-label={t("dashboard.amkaPlaceholder")}
                placeholder={t("dashboard.amkaPlaceholder")}
                className="mono flex-1 rounded-lg border border-brand-200 bg-white px-4 py-3 text-[15px] tracking-wide text-slate-900 outline-none placeholder:font-sans placeholder:tracking-normal placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-brand-500/30 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:ring-brand-500/20"
              />
              <input
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                inputMode="numeric"
                maxLength={6}
                aria-label={t("dashboard.pinPlaceholder")}
                placeholder={t("dashboard.pinPlaceholder")}
                className="mono rounded-lg border border-brand-200 bg-white px-4 py-3 text-[15px] tracking-[0.3em] text-slate-900 outline-none placeholder:font-sans placeholder:tracking-normal placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-brand-500/30 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:ring-brand-500/20 sm:w-32"
              />
              <button
                type="submit"
                className="shrink-0 rounded-lg border border-brand-600 bg-white px-6 py-3 text-[14px] font-semibold text-brand-700 shadow-card transition-colors hover:bg-brand-50 dark:bg-slate-900 dark:text-brand-300 dark:hover:bg-slate-800"
              >
                {t("dashboard.lookUp")}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

/* ── status chip for an in-progress row ── */
function StatusChip({
  meta,
  status,
}: {
  meta: AlertMeta | undefined;
  status: QueueItem["status"];
}) {
  const { t } = useTranslation();
  if (meta?.hasBlock) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11.5px] font-semibold text-red-700 dark:bg-red-500/15 dark:text-red-400">
        <AlertCircleIcon width={12} height={12} />{" "}
        {t("dashboard.alertsCount", { count: meta.count })}
      </span>
    );
  }
  if (meta && meta.count > 0) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11.5px] font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
        <AlertTriangleIcon width={12} height={12} />{" "}
        {t("dashboard.alertsCount", { count: meta.count })}
      </span>
    );
  }
  if (status === "FLAGGED") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11.5px] font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
        <FlagIcon width={12} height={12} /> {t("dashboard.statusFlagged")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11.5px] font-semibold text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400">
      <CheckIcon width={12} height={12} strokeWidth={3} /> {t("dashboard.ok")}
    </span>
  );
}

/* ── In progress list ── */
function InProgressList({
  items,
  alertsByRx,
}: {
  items: QueueItem[];
  alertsByRx: Map<string, AlertMeta>;
}) {
  const { t } = useTranslation();
  return (
    <section>
      <div className="mb-2.5 flex items-center gap-2">
        <h3 className="text-[14px] font-bold text-slate-900 dark:text-slate-100">
          {t("dashboard.inProgress")}
        </h3>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11.5px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
          {items.length}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white/50 px-4 py-3 text-[13px] italic text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          {t("dashboard.inProgressEmpty")}
        </p>
      ) : (
        <div className="card overflow-hidden">
          {items.map((it, i) => {
            const meta = alertsByRx.get(it.rxId);
            return (
              <Link
                key={it.rxId}
                to={`/prescription/${it.rxId}`}
                className={`group relative flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60 ${
                  i > 0 ? "border-t border-slate-100 dark:border-slate-800" : ""
                }`}
              >
                {meta?.hasBlock && <span className="absolute left-0 top-0 h-full w-1 bg-red-500" />}
                <span className="mono w-[120px] shrink-0 truncate text-[13px] text-slate-500 dark:text-slate-400">
                  {it.rxId}
                </span>
                <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-slate-900 dark:text-slate-100">
                  {it.patientName}
                </span>
                <StatusChip meta={meta} status={it.status} />
                <span className="text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600 dark:text-slate-600 dark:group-hover:text-brand-400">
                  <ChevronRightIcon width={16} height={16} />
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

/* ── Today (completed) list ── */
function TodayList({ items }: { items: QueueItem[] }) {
  const { t } = useTranslation();
  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-bold text-slate-900 dark:text-slate-100">
            {t("dashboard.today")}
          </h3>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11.5px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            {items.length}
          </span>
        </div>
        <Link
          to="/history"
          className="flex items-center gap-0.5 text-[12.5px] font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400"
        >
          {t("dashboard.fullHistory")} →
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white/50 px-4 py-3 text-[13px] italic text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          {t("dashboard.todayEmpty")}
        </p>
      ) : (
        <div className="card overflow-hidden">
          {items.map((it, i) => (
            <Link
              key={it.rxId}
              to={`/prescription/${it.rxId}`}
              className={`flex items-center gap-4 px-4 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60 ${
                i > 0 ? "border-t border-slate-100 dark:border-slate-800" : ""
              }`}
            >
              <span className="shrink-0 text-emerald-500 dark:text-emerald-400">
                <CheckCircleIcon width={16} height={16} />
              </span>
              <span className="mono hidden w-[88px] shrink-0 text-[12.5px] text-slate-400 dark:text-slate-500 sm:block">
                {it.rxId}
              </span>
              <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-slate-800 dark:text-slate-200">
                {it.patientName}
              </span>
              <span className="hidden truncate text-[12.5px] text-slate-500 dark:text-slate-400 md:block md:w-[150px]">
                {it.medication}
              </span>
              <span className="mono shrink-0 text-[12.5px] text-slate-400 dark:text-slate-500">
                {it.date}
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
