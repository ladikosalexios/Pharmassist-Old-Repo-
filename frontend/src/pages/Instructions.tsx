import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircleIcon,
  CheckIcon,
  ChevronLeftIcon,
  FileTextIcon,
  MailIcon,
  PrinterIcon,
  SendIcon,
} from "../components/Icons";
import { useToast } from "../components/Toast";
import {
  ApiError,
  createDocumentationEntry,
  getPrescription,
  listPrescriptions,
  sendInstructions,
} from "../lib/api";
import { defaultAdditionalNotes, renderInstructions } from "../lib/instructions";
import type { DeliveryMethod, InstructionsLanguage, Prescription, QueueItem } from "../types";

// `label` is the canonical English string persisted to the documentation log
// (the API contract) — never translate it. `labelKey` drives the visible text.
const LANGUAGE_OPTIONS: {
  value: InstructionsLanguage;
  label: string;
  labelKey: string;
}[] = [
  { value: "el", label: "Greek", labelKey: "instructions.languageGreek" },
  { value: "en", label: "English", labelKey: "instructions.languageEnglish" },
  { value: "other", label: "Other (English template)", labelKey: "instructions.languageOther" },
];

const METHOD_OPTIONS: { value: DeliveryMethod; labelKey: string }[] = [
  { value: "PRINT", labelKey: "instructions.methodPrint" },
  { value: "DIGITAL", labelKey: "instructions.methodDigital" },
  { value: "BOTH", labelKey: "instructions.methodBoth" },
];

const SETTING_OPTIONS = [
  { value: "Private", labelKey: "instructions.settingPrivate" },
  { value: "Hospital", labelKey: "instructions.settingHospital" },
] as const;

type Setting = (typeof SETTING_OPTIONS)[number]["value"];

const INPUT_CLASS =
  "w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3.5 py-2.5 text-[14px] text-slate-900 dark:text-slate-100 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

export function Instructions() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [search, setSearch] = useSearchParams();
  const initialRxId = search.get("rxId") ?? "";

  // Eligible prescriptions for the dropdown — completed, plus the rx that
  // landed us here (if it isn't completed yet, still surface it).
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

  // Selected prescription detail.
  const [rxId, setRxId] = useState<string>(initialRxId);
  const [rx, setRx] = useState<Prescription | null>(null);
  const [rxLoading, setRxLoading] = useState(false);
  const [rxError, setRxError] = useState<string | null>(null);

  // Form state.
  const [language, setLanguage] = useState<InstructionsLanguage>("el");
  const [method, setMethod] = useState<DeliveryMethod>("BOTH");
  const [setting, setSetting] = useState<Setting>("Private");
  const [notes, setNotes] = useState<string>("");
  const [includeSideEffects, setIncludeSideEffects] = useState<boolean>(true);
  const [includeLifestyle, setIncludeLifestyle] = useState<boolean>(true);

  // Async UI state for actions.
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load the queue once for the dropdown.
  useEffect(() => {
    let active = true;
    listPrescriptions()
      .then((items) => {
        if (active) setQueue(items);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setQueueError(e instanceof ApiError ? e.message : t("instructions.loadQueueError"));
      });
    return () => {
      active = false;
    };
  }, [t]);

  // When the selected rxId changes, fetch the full prescription and pre-fill notes.
  useEffect(() => {
    if (!rxId) {
      setRx(null);
      return;
    }
    let active = true;
    setRxLoading(true);
    setRxError(null);
    getPrescription(rxId)
      .then((data) => {
        if (!active) return;
        setRx(data);
        setNotes(defaultAdditionalNotes(data, language));
      })
      .catch((e: unknown) => {
        if (!active) return;
        setRxError(e instanceof ApiError ? e.message : t("instructions.loadRxError"));
      })
      .finally(() => {
        if (active) setRxLoading(false);
      });
    return () => {
      active = false;
    };
    // We deliberately don't re-fetch when language alone changes; the notes
    // prefill only re-runs on rxId switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rxId]);

  // When language changes, refresh the prefill if the user hasn't customised it.
  useEffect(() => {
    if (!rx) return;
    setNotes((prev) => {
      const seedEl = defaultAdditionalNotes(rx, "el");
      const seedEn = defaultAdditionalNotes(rx, "en");
      if (prev === "" || prev === seedEl || prev === seedEn) {
        return defaultAdditionalNotes(rx, language);
      }
      return prev;
    });
  }, [language, rx]);

  // Sync rxId into the URL so refreshes preserve context.
  useEffect(() => {
    const next = new URLSearchParams(search);
    if (rxId) next.set("rxId", rxId);
    else next.delete("rxId");
    if (next.toString() !== search.toString()) setSearch(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rxId]);

  const eligible = useMemo(() => {
    if (!queue) return [];
    const seen = new Set<string>();
    const items: QueueItem[] = [];
    for (const q of queue) {
      if (q.status === "COMPLETED" || q.rxId === rxId) {
        if (!seen.has(q.rxId)) {
          seen.add(q.rxId);
          items.push(q);
        }
      }
    }
    return items;
  }, [queue, rxId]);

  const preview = useMemo(() => {
    if (!rx) return "";
    return renderInstructions(rx, language, {
      additionalNotes: notes,
      includeSideEffects,
      includeLifestyle,
    });
  }, [rx, language, notes, includeSideEffects, includeLifestyle]);

  function onPrint() {
    if (!preview) return;
    window.print();
  }

  async function onSend() {
    if (!rx) return;
    setSending(true);
    try {
      await sendInstructions({
        rxId: rx.rxId,
        patientId: rx.patient.amka,
        content: preview,
        method,
      });
      const methodLabel = t(METHOD_OPTIONS.find((o) => o.value === method)?.labelKey ?? "");
      toast(t("instructions.toastSent", { method: methodLabel, rxId: rx.rxId }), "success");
    } catch (e) {
      toast(
        e instanceof ApiError
          ? t("instructions.toastSendFailed", { error: e.message })
          : t("instructions.toastSendFailedGeneric"),
        "error",
      );
    } finally {
      setSending(false);
    }
  }

  async function onSaveToLog() {
    if (!rx) return;
    setSaving(true);
    try {
      const created = await createDocumentationEntry({
        rxId: rx.rxId,
        instructions: preview,
        // Persist the canonical English label — this is the API contract.
        language: LANGUAGE_OPTIONS.find((o) => o.value === language)?.label ?? language,
        method,
        setting,
      });
      toast(t("instructions.toastSaved", { id: created.id }), "success");
    } catch (e) {
      toast(
        e instanceof ApiError
          ? t("instructions.toastSaveFailed", { error: e.message })
          : t("instructions.toastSaveFailedGeneric"),
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1100px] p-8">
      <div className="mb-3 print:hidden">
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1 text-[13px] font-medium text-brand-600 dark:text-brand-400 transition-colors hover:text-brand-700"
        >
          <ChevronLeftIcon width={14} height={14} /> {t("instructions.backToDashboard")}
        </Link>
      </div>

      <header className="mb-6 print:hidden">
        <h1 className="text-[24px] font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("instructions.title")}
        </h1>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
          {t("instructions.subtitle")}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 print:block">
        {/* Form */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-card print:hidden">
          <h2 className="mb-4 text-[16px] font-bold text-slate-900 dark:text-slate-100">
            {t("instructions.formTitle")}
          </h2>

          {queueError && (
            <div
              role="alert"
              className="mb-3 flex items-start gap-2.5 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3.5 py-3 text-[13px] text-amber-800 dark:text-amber-200 animate-alert-in"
            >
              <span className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400">
                <AlertCircleIcon width={16} height={16} />
              </span>
              <div>
                <div className="font-semibold">{t("instructions.queueErrorTitle")}</div>
                <div className="text-amber-700/90 dark:text-amber-400/90">{queueError}</div>
              </div>
            </div>
          )}

          <Field label={t("instructions.prescriptionLabel")}>
            <select value={rxId} onChange={(e) => setRxId(e.target.value)} className={INPUT_CLASS}>
              <option value="" disabled>
                {t("instructions.prescriptionPlaceholder")}
              </option>
              {eligible.map((q) => (
                <option key={q.rxId} value={q.rxId}>
                  {q.rxId} — {q.patientName} · {q.medication}
                </option>
              ))}
            </select>
          </Field>

          {rxError && (
            <div
              role="alert"
              className="mt-3 flex items-start gap-2.5 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3.5 py-3 text-[13px] text-red-700 dark:text-red-400 animate-alert-in"
            >
              <span className="mt-0.5 shrink-0 text-red-600 dark:text-red-400">
                <AlertCircleIcon width={16} height={16} />
              </span>
              <div>
                <div className="font-semibold">{t("instructions.rxErrorTitle")}</div>
                <div className="text-red-600/90 dark:text-red-400/90">{rxError}</div>
              </div>
            </div>
          )}

          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label={t("instructions.languageLabel")}>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as InstructionsLanguage)}
                className={INPUT_CLASS}
              >
                {LANGUAGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {t(o.labelKey)}
                  </option>
                ))}
              </select>
            </Field>

            <Field label={t("instructions.methodLabel")}>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as DeliveryMethod)}
                className={INPUT_CLASS}
              >
                {METHOD_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {t(o.labelKey)}
                  </option>
                ))}
              </select>
            </Field>

            <Field label={t("instructions.settingLabel")}>
              <select
                value={setting}
                onChange={(e) => setSetting(e.target.value as Setting)}
                className={INPUT_CLASS}
              >
                {SETTING_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {t(o.labelKey)}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label={t("instructions.notesLabel")}>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("instructions.notesPlaceholder")}
              className={`min-h-[140px] resize-vertical placeholder:text-slate-400 dark:placeholder:text-slate-500 ${INPUT_CLASS}`}
            />
          </Field>

          <div className="mt-4 space-y-2">
            <Checkbox
              label={t("instructions.includeSideEffects")}
              checked={includeSideEffects}
              onChange={setIncludeSideEffects}
            />
            <Checkbox
              label={t("instructions.includeLifestyle")}
              checked={includeLifestyle}
              onChange={setIncludeLifestyle}
            />
          </div>

          <div className="mt-6 flex flex-wrap gap-2 border-t border-slate-200 dark:border-slate-800 pt-4">
            <button
              type="button"
              onClick={onPrint}
              disabled={!preview}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-[13px] font-semibold text-slate-700 dark:text-slate-200 shadow-card transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <PrinterIcon width={15} height={15} /> {t("instructions.print")}
            </button>
            <button
              type="button"
              onClick={onSend}
              disabled={!preview || sending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {sending ? (
                <span className="spinner" />
              ) : method === "DIGITAL" ? (
                <MailIcon width={15} height={15} />
              ) : (
                <SendIcon width={15} height={15} />
              )}
              {sending ? t("instructions.sending") : t("instructions.send")}
            </button>
            <button
              type="button"
              onClick={onSaveToLog}
              disabled={!preview || saving}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-[13px] font-semibold text-slate-700 dark:text-slate-200 shadow-card transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? <span className="spinner" /> : <CheckIcon width={15} height={15} />}
              {saving ? t("instructions.saving") : t("instructions.save")}
            </button>
          </div>
        </section>

        {/* Preview — id + inner <pre> are required by the @media print rules in index.css. */}
        <section
          id="instructions-preview"
          className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-card"
        >
          <header className="mb-4 flex items-start justify-between gap-3 print:hidden">
            <div>
              <h2 className="text-[16px] font-bold text-slate-900 dark:text-slate-100">
                {t("instructions.previewTitle")}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t("instructions.previewSubtitle")}
              </p>
            </div>
            {rx && (
              <span className="mono inline-flex items-center rounded-full bg-brand-50 dark:bg-brand-500/10 px-2 py-0.5 text-[11.5px] font-semibold text-brand-700 dark:text-brand-300">
                {rx.rxId}
              </span>
            )}
          </header>

          {rxLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span className="spinner text-brand-600" /> {t("instructions.loadingRx")}
            </div>
          ) : !rx ? (
            <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-6 py-10 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 dark:bg-brand-500/10 text-brand-500 dark:text-brand-400">
                <FileTextIcon width={22} height={22} />
              </div>
              <h3 className="mt-3.5 text-[15px] font-bold text-slate-900 dark:text-slate-100">
                {t("instructions.emptyTitle")}
              </h3>
              <p className="mt-1.5 max-w-[300px] text-[13px] text-slate-500 dark:text-slate-400">
                {t("instructions.emptyBody")}
              </p>
            </div>
          ) : (
            <pre
              aria-live="polite"
              className="whitespace-pre-wrap rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 font-sans text-[13px] leading-relaxed text-slate-800 dark:text-slate-200"
            >
              {preview}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
        {label}
      </span>
      {children}
    </label>
  );
}

function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-[13px] text-slate-700 dark:text-slate-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-slate-300 dark:border-slate-600 text-brand-600 focus:ring-brand-100"
      />
      <span>{label}</span>
    </label>
  );
}
