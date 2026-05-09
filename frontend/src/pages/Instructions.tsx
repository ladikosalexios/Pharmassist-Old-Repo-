import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertCircleIcon,
  CheckIcon,
  ChevronLeftIcon,
  DownloadIcon,
  FileTextIcon,
  MailIcon,
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

const LANGUAGE_OPTIONS: { value: InstructionsLanguage; label: string }[] = [
  { value: "el", label: "Greek" },
  { value: "en", label: "English" },
  { value: "other", label: "Other (English template)" },
];

const METHOD_OPTIONS: { value: DeliveryMethod; label: string }[] = [
  { value: "PRINT", label: "Print only" },
  { value: "DIGITAL", label: "Digital only" },
  { value: "BOTH", label: "Both" },
];

const SETTING_OPTIONS = [
  { value: "Private", label: "Private" },
  { value: "Hospital", label: "Hospital" },
] as const;

type Setting = (typeof SETTING_OPTIONS)[number]["value"];

export function Instructions() {
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
        setQueueError(e instanceof ApiError ? e.message : "Could not load the prescription queue.");
      });
    return () => {
      active = false;
    };
  }, []);

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
        setRxError(e instanceof ApiError ? e.message : "Could not load this prescription.");
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
        patientId: rx.patient.id,
        content: preview,
        method,
      });
      toast(`Instructions sent (${method.toLowerCase()}) for ${rx.rxId}`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? `Send failed: ${e.message}` : "Send failed.", "error");
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
        language: LANGUAGE_OPTIONS.find((o) => o.value === language)?.label ?? language,
        method,
        setting,
      });
      toast(`Saved to documentation log (${created.id}).`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? `Save failed: ${e.message}` : "Save failed.", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-3 print:hidden">
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
        >
          <ChevronLeftIcon width={14} height={14} /> Back to Dashboard
        </Link>
      </div>

      <header className="mb-6 print:hidden">
        <h1 className="text-2xl font-bold text-slate-900">Generate Patient Instructions</h1>
        <p className="mt-1 text-sm text-slate-500">
          Compose, preview, and dispatch personalised counselling notes for an approved
          prescription.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 print:block">
        {/* Form */}
        <section className="card p-6 print:hidden">
          <h2 className="mb-4 text-base font-semibold text-slate-900">Form</h2>

          {queueError && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>Could not load the queue: {queueError}</span>
            </div>
          )}

          <Field label="Prescription">
            <select
              value={rxId}
              onChange={(e) => setRxId(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
            >
              <option value="" disabled>
                Select a prescription…
              </option>
              {eligible.map((q) => (
                <option key={q.rxId} value={q.rxId}>
                  {q.rxId} — {q.patientName} · {q.medication}
                </option>
              ))}
            </select>
          </Field>

          {rxError && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{rxError}</span>
            </div>
          )}

          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Language">
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as InstructionsLanguage)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
              >
                {LANGUAGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Delivery Method">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as DeliveryMethod)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
              >
                {METHOD_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Setting">
              <select
                value={setting}
                onChange={(e) => setSetting(e.target.value as Setting)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
              >
                {SETTING_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="Additional Notes">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Pre-filled with key SPC points for this drug. Edit as needed."
              className="min-h-[140px] w-full resize-vertical rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
            />
          </Field>

          <div className="mt-4 space-y-2">
            <Checkbox
              label="Include side effect warnings"
              checked={includeSideEffects}
              onChange={setIncludeSideEffects}
            />
            <Checkbox
              label="Include dietary / lifestyle advice"
              checked={includeLifestyle}
              onChange={setIncludeLifestyle}
            />
          </div>

          <div className="mt-6 flex flex-wrap gap-2 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={onPrint}
              disabled={!preview}
              className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <DownloadIcon /> Print
            </button>
            <button
              type="button"
              onClick={onSend}
              disabled={!preview || sending}
              className="btn btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {sending ? (
                <span className="spinner" />
              ) : method === "DIGITAL" ? (
                <MailIcon />
              ) : (
                <SendIcon />
              )}
              {sending ? "Sending…" : "Send Digital"}
            </button>
            <button
              type="button"
              onClick={onSaveToLog}
              disabled={!preview || saving}
              className="btn btn-success disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {saving ? <span className="spinner" /> : <CheckIcon />}
              {saving ? "Saving…" : "Save to Log"}
            </button>
          </div>
        </section>

        {/* Preview */}
        <section id="instructions-preview" className="card p-6" aria-live="polite">
          <header className="mb-4 flex items-start justify-between gap-3 print:hidden">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Preview</h2>
              <p className="text-xs text-slate-500">Live — updates as you edit the form.</p>
            </div>
            {rx && (
              <span className="chip border border-brand-100 bg-brand-50 text-brand-700">
                {rx.rxId}
              </span>
            )}
          </header>

          {rxLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span className="spinner text-brand-600" /> Loading prescription…
            </div>
          ) : !rx ? (
            <div className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
              <FileTextIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>Select a prescription to start drafting instructions.</span>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-4 font-sans text-[13px] leading-relaxed text-slate-800">
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
      <span className="mb-1.5 block text-[13px] font-medium text-slate-600">{label}</span>
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
    <label className="flex cursor-pointer items-start gap-2.5 text-[13px] text-slate-700">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-100"
      />
      <span>{label}</span>
    </label>
  );
}
