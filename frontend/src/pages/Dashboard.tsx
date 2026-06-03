import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  BarcodeIcon,
  CheckCircleIcon,
  CheckIcon,
  ChevronRightIcon,
  FileTextIcon,
  FlagIcon,
  KeyIcon,
  ShieldIcon,
} from "../components/Icons";
import { SafetyAlertsPanel } from "../components/SafetyAlertsPanel";
import { useKeyboardShortcuts } from "../lib/keyboard";
import { useAuth } from "../lib/auth";
import { ApiError, listPrescriptions } from "../lib/api";
import type { QueueItem } from "../types";

type HeroTab = "barcode" | "paperless";

export function Dashboard() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();

  // Greek locale for the header date when the UI is in Greek; matches HMVO's
  // Greek-first requirement and the design reference (e.g. "Σάββατο, 31 Μαΐου 2026").
  const localeTag = i18n.language?.startsWith("en") ? "en-GB" : "el-GR";
  const today = new Date().toLocaleDateString(localeTag, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

  const scannerRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    listPrescriptions()
      .then((items) => {
        if (active) setQueue(items);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setQueueError(e instanceof ApiError ? e.message : t("counter.queueError"));
      });
    return () => {
      active = false;
    };
  }, [t]);

  // ⌘K / Ctrl-K focuses the scanner input. Uses the global shortcut hook but
  // bypasses the input-focus guard so the shortcut still works while the
  // scanner is already focused (re-focusing is a no-op but matches the
  // discoverable contract advertised in the hint below the page).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        scannerRef.current?.focus();
        scannerRef.current?.select();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Single-key 's' jumps focus into the scanner — keeps parity with the rest
  // of the app's discoverable shortcuts (useKeyboardShortcuts already skips
  // input targets, so 's' typed inside a field still goes into the field).
  useKeyboardShortcuts({
    s: () => scannerRef.current?.focus(),
  });

  const { inProgress, todayItems } = useMemo(() => splitQueue(queue ?? []), [queue]);

  const pharmacy = user?.pharmacy ?? "";

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-8">
      {/* header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-bold tracking-tight text-slate-900">
            {t("counter.title")}
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            {today} · <span className="font-medium text-slate-600">{pharmacy}</span>
          </p>
        </div>
        <Link
          to="/instructions"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900"
        >
          <FileTextIcon width={15} height={15} />
          {t("common.instructions")}
        </Link>
      </div>

      {/* hero */}
      <ScanHero
        scannerRef={scannerRef}
        onScanBarcode={(barcode) => navigate(`/prescription/${encodeURIComponent(barcode)}`)}
      />

      {/* error toast for the queue (rare — most calls succeed) */}
      {queueError && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{queueError}</span>
        </div>
      )}

      {/* two-col below hero */}
      <div className="mt-7 grid grid-cols-1 gap-7 lg:grid-cols-[1fr_320px]">
        <div className="space-y-7">
          <InProgress items={inProgress} loading={queue === null} />
          <Today items={todayItems} loading={queue === null} />
        </div>
        <div>
          <SafetyAlertsPanel />
        </div>
      </div>

      {/* shortcut hint */}
      <div className="mt-8 flex items-center justify-center gap-1.5 text-[12px] text-slate-400">
        <kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-sans text-[11px] font-semibold text-slate-500 shadow-card">
          ⌘K
        </kbd>
        {t("counter.shortcutHint")}
      </div>
    </div>
  );
}

interface ScanHeroProps {
  scannerRef: React.RefObject<HTMLInputElement>;
  onScanBarcode: (barcode: string) => void;
}

function ScanHero({ scannerRef, onScanBarcode }: ScanHeroProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<HeroTab>("barcode");
  const [barcode, setBarcode] = useState("");
  const [amka, setAmka] = useState("");
  const [pin, setPin] = useState("");

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-cardLg">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[17px] font-bold text-slate-900">{t("counter.hero.title")}</h2>
          <p className="mt-0.5 text-[13px] text-slate-500">{t("counter.hero.subtitle")}</p>
        </div>
        {/* pill tabs */}
        <div
          role="tablist"
          aria-label={t("counter.hero.title")}
          className="flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 p-1"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === "barcode"}
            onClick={() => setTab("barcode")}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors ${
              tab === "barcode"
                ? "bg-white text-brand-700 shadow-card"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <BarcodeIcon width={15} height={15} /> {t("counter.hero.tabBarcode")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "paperless"}
            onClick={() => setTab("paperless")}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors ${
              tab === "paperless"
                ? "bg-white text-brand-700 shadow-card"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <KeyIcon width={15} height={15} /> {t("counter.hero.tabPaperless")}
          </button>
        </div>
      </div>

      <div className="rounded-xl bg-brand-50 p-6">
        {tab === "barcode" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = barcode.trim();
              if (trimmed) onScanBarcode(trimmed);
            }}
          >
            <div className="mb-3 flex items-center gap-2.5 text-brand-700">
              <BarcodeIcon width={22} height={22} />
              <span className="text-[14px] font-semibold">{t("counter.hero.barcodeLabel")}</span>
            </div>
            <div className="flex gap-2.5">
              <input
                ref={scannerRef}
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                autoFocus
                inputMode="numeric"
                placeholder={t("counter.hero.barcodePlaceholder")}
                className="flex-1 rounded-lg border border-brand-200 bg-white px-4 py-3 font-mono text-[16px] tracking-wide text-slate-900 placeholder:font-sans placeholder:tracking-normal placeholder:text-slate-400 outline-none transition-shadow focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              />
              <button
                type="submit"
                disabled={barcode.trim().length === 0}
                className="shrink-0 rounded-lg bg-brand-600 px-7 text-[14px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-brand-600/40"
              >
                {t("counter.hero.barcodeOpen")}
              </button>
            </div>
            <p className="mt-2.5 font-mono text-[11.5px] text-brand-600/70">
              {t("counter.hero.barcodeRouteHint")}
            </p>
          </form>
        ) : (
          <PaperlessForm amka={amka} pin={pin} onAmkaChange={setAmka} onPinChange={setPin} />
        )}
      </div>
    </div>
  );
}

interface PaperlessFormProps {
  amka: string;
  pin: string;
  onAmkaChange: (v: string) => void;
  onPinChange: (v: string) => void;
}

function PaperlessForm({ amka, pin, onAmkaChange, onPinChange }: PaperlessFormProps) {
  const { t } = useTranslation();
  return (
    <form
      onSubmit={(e) => {
        // Submission intentionally disabled until backend route lands.
        e.preventDefault();
      }}
    >
      <div className="mb-3 flex items-center gap-2.5 text-brand-700">
        <ShieldIcon width={22} height={22} />
        <span className="text-[14px] font-semibold">{t("counter.hero.amkaTitle")}</span>
      </div>
      <div className="flex flex-col gap-2.5 sm:flex-row">
        <input
          value={amka}
          onChange={(e) => onAmkaChange(e.target.value)}
          inputMode="numeric"
          maxLength={11}
          placeholder={t("counter.hero.amkaPlaceholder")}
          className="flex-1 rounded-lg border border-brand-200 bg-white px-4 py-3 font-mono text-[15px] tracking-wide text-slate-900 placeholder:font-sans placeholder:tracking-normal placeholder:text-slate-400 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
        <input
          value={pin}
          onChange={(e) => onPinChange(e.target.value)}
          inputMode="numeric"
          maxLength={6}
          placeholder={t("counter.hero.pinPlaceholder")}
          className="w-full rounded-lg border border-brand-200 bg-white px-4 py-3 font-mono text-[15px] tracking-[0.3em] text-slate-900 placeholder:font-sans placeholder:tracking-normal placeholder:text-slate-400 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 sm:w-32"
        />
        <button
          type="submit"
          disabled
          title={t("counter.hero.comingSoon")}
          className="shrink-0 cursor-not-allowed rounded-lg border border-brand-200 bg-white px-6 py-3 text-[14px] font-semibold text-brand-400 shadow-card"
        >
          {t("counter.hero.comingSoon")}
        </button>
      </div>
      <p className="mt-2.5 font-mono text-[11.5px] text-brand-600/70">
        {t("counter.hero.amkaRouteHint")}
      </p>
    </form>
  );
}

interface SectionListProps<T> {
  items: T[];
  loading: boolean;
}

function InProgress({ items, loading }: SectionListProps<QueueItem>) {
  const { t } = useTranslation();
  return (
    <section>
      <div className="mb-2.5 flex items-center gap-2">
        <h3 className="text-[14px] font-bold text-slate-900">{t("counter.inProgress.title")}</h3>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11.5px] font-semibold text-slate-500">
          {loading ? "—" : items.length}
        </span>
      </div>
      {loading ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white/50 px-4 py-3 text-[13px] italic text-slate-400">
          <span className="spinner mr-2 text-brand-600" />
          {t("shell.loading")}
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white/50 px-4 py-3 text-[13px] italic text-slate-500">
          {t("counter.inProgress.empty")}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
          {items.map((rx, i) => (
            <InProgressRow key={rx.rxId} rx={rx} divider={i > 0} />
          ))}
        </div>
      )}
    </section>
  );
}

function InProgressRow({ rx, divider }: { rx: QueueItem; divider: boolean }) {
  const isFlagged = rx.status === "FLAGGED";
  return (
    <Link
      to={`/prescription/${encodeURIComponent(rx.rxId)}`}
      className={`group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-slate-50 ${
        divider ? "border-t border-slate-100" : ""
      } ${isFlagged ? "relative" : ""}`}
    >
      {isFlagged && <span className="absolute left-0 top-0 h-full w-1 bg-red-500"></span>}
      <span className="w-[120px] shrink-0 truncate font-mono text-[13px] text-slate-500">
        {rx.rxId}
      </span>
      <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-slate-900">
        {rx.patientName}
      </span>
      <StatusChip status={rx.status} />
      <span className="hidden w-[150px] shrink-0 truncate text-right text-[12px] text-slate-400 lg:block">
        {rx.medication}
      </span>
      <span className="shrink-0 text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600">
        <ChevronRightIcon width={16} height={16} />
      </span>
    </Link>
  );
}

function StatusChip({ status }: { status: QueueItem["status"] }) {
  const { t } = useTranslation();
  if (status === "FLAGGED") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11.5px] font-semibold text-red-700">
        <AlertCircleIcon width={12} height={12} />{" "}
        {t("counter.inProgress.alertsSuffix", { count: 1 })}
      </span>
    );
  }
  if (status === "PENDING") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11.5px] font-semibold text-amber-700">
        <AlertTriangleIcon width={12} height={12} /> {t("counter.inProgress.ok")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11.5px] font-semibold text-emerald-600">
      <CheckIcon width={12} height={12} strokeWidth={3} /> {t("counter.inProgress.ok")}
    </span>
  );
}

function Today({ items, loading }: SectionListProps<QueueItem>) {
  const { t } = useTranslation();
  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-bold text-slate-900">{t("counter.today.title")}</h3>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11.5px] font-semibold text-slate-500">
            {loading ? "—" : items.length}
          </span>
        </div>
        <Link
          to="/documentation"
          className="flex items-center gap-0.5 text-[12.5px] font-medium text-brand-600 hover:text-brand-700"
        >
          {t("counter.today.fullHistory")}
        </Link>
      </div>
      {loading ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white/50 px-4 py-3 text-[13px] italic text-slate-400">
          <span className="spinner mr-2 text-brand-600" />
          {t("shell.loading")}
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white/50 px-4 py-3 text-[13px] italic text-slate-500">
          {t("counter.today.empty")}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
          {items.map((rx, i) => (
            <TodayRow key={rx.rxId} rx={rx} divider={i > 0} />
          ))}
        </div>
      )}
    </section>
  );
}

function TodayRow({ rx, divider }: { rx: QueueItem; divider: boolean }) {
  const { t } = useTranslation();
  // No discrete "flagged in today's history" signal on a COMPLETED queue item
  // — the FLAGGED row falls into the in-progress list, not here. Today's rows
  // are completed dispenses with the safety check at action-time recorded
  // elsewhere; we keep the visual hook for future use.
  const flagged = false;
  return (
    <Link
      to={`/prescription/${encodeURIComponent(rx.rxId)}`}
      className={`flex items-center gap-4 px-4 py-3 transition-colors hover:bg-slate-50 ${
        divider ? "border-t border-slate-100" : ""
      }`}
    >
      <span className={`shrink-0 ${flagged ? "text-amber-600" : "text-emerald-500"}`}>
        {flagged ? <FlagIcon width={16} height={16} /> : <CheckCircleIcon width={16} height={16} />}
      </span>
      <span className="hidden w-[58px] shrink-0 truncate font-mono text-[12.5px] text-slate-400 sm:block">
        {rx.rxId.length > 4 ? `…${rx.rxId.slice(-4)}` : rx.rxId}
      </span>
      <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-slate-800">
        {rx.patientName}
      </span>
      <span className="hidden truncate text-[12.5px] text-slate-500 md:block md:w-[150px]">
        {rx.medication}
      </span>
      {flagged && (
        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
          {t("counter.today.flagged")}
        </span>
      )}
    </Link>
  );
}

function splitQueue(queue: QueueItem[]): { inProgress: QueueItem[]; todayItems: QueueItem[] } {
  // PENDING + FLAGGED → in-progress (active workflows the pharmacist hasn't
  // closed). COMPLETED → today's tally. Anything else is silently ignored.
  const inProgress = queue.filter((q) => q.status === "PENDING" || q.status === "FLAGGED");
  const todayItems = queue.filter((q) => q.status === "COMPLETED");
  return { inProgress, todayItems };
}
