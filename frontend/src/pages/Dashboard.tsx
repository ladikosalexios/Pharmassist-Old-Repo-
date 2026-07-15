import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { BarcodeIcon, KeyIcon, ShieldIcon } from "../components/Icons";
import { useAuth } from "../lib/auth";
import { useToast } from "../components/Toast";

// Platform-aware shortcut hint (⌘K on Apple, Ctrl+K elsewhere). Computed once;
// `navigator` is always present in the browser, guarded for SSR/tests.
const IS_APPLE =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || "");

// Thin home. The pharmacist's real workflow lives in their pharmacy software +
// the scan-riding agent (docs/agent-vs-spa-surface-split.md); the SPA is the
// deep-work console you drop into for a specific prescription — via the agent's
// ⌘⌥↵ handoff, or by scanning / entering a barcode here. The old prescription
// queue + active-alerts rail were retired: ΗΔΥΚΑ has no pull-based queue, and
// alerts now surface at scan time.
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

      <div className="mx-auto w-full max-w-[760px] px-4 py-6 sm:px-6 lg:px-8">
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

// Paperless (AMKA + PIN) lookup is hidden until Phase 2 wires the backend
// `/prescriptions/nopaper` retrieval. The barcode tab already resolves paperless
// (άυλη) prescriptions via GET /prescriptions/get/{barcode}, so the separate
// AMKA+PIN entry is only a fallback. Flip to `true` once that endpoint lands.
const SHOW_PAPERLESS: boolean = false;

/* ── "Scan to review" scanner hero ── */
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
        {SHOW_PAPERLESS && (
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
        )}
      </div>

      <div className="rounded-xl bg-brand-50 p-5 dark:bg-brand-500/10 sm:p-6">
        {!SHOW_PAPERLESS || tab === "barcode" ? (
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
