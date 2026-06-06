import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { CheckCircleIcon, DownloadIcon, XIcon, AlertCircleIcon, FileTextIcon } from "./Icons";
import { ApiError, exportDocumentationRecord, getDocumentationRecord } from "../lib/api";
import { useToast } from "./Toast";
import { useModalRegistration } from "../lib/keyboard";
import type { DeliveryMethod, DocumentationRecord } from "../types";

interface DocumentationDetailModalProps {
  open: boolean;
  recordId: string | null;
  onClose: () => void;
}

const METHOD_TONE: Record<DeliveryMethod, string> = {
  PRINT: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-400",
  DIGITAL: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-400",
  BOTH: "bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-400",
};

const METHOD_LABEL: Record<DeliveryMethod, string> = {
  PRINT: "Print",
  DIGITAL: "Digital",
  BOTH: "Print + Digital",
};

export function DocumentationDetailModal({
  open,
  recordId,
  onClose,
}: DocumentationDetailModalProps) {
  useModalRegistration(open);
  const titleId = useId();
  const { toast } = useToast();
  const [record, setRecord] = useState<DocumentationRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!open || !recordId) return;
    let active = true;
    setLoading(true);
    setError(null);
    setRecord(null);
    getDocumentationRecord(recordId)
      .then((data) => {
        if (active) setRecord(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load this record.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, recordId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !exporting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, exporting, onClose]);

  if (!open) return null;

  async function onExport() {
    if (!record) return;
    setExporting(true);
    try {
      await exportDocumentationRecord(record.id);
      toast(`Exported ${record.id}`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? `Export failed: ${e.message}` : "Export failed.", "error");
    } finally {
      setExporting(false);
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 animate-fade-in"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !exporting) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-cardLg dark:bg-slate-900"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-400">
              <FileTextIcon />
            </div>
            <div>
              <h2
                id={titleId}
                className="text-base font-semibold text-slate-900 dark:text-slate-100"
              >
                Documentation Record
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {record?.id ? <span className="font-mono">{record.id}</span> : recordId}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={exporting}
            aria-label="Close detail"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <XIcon />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span className="spinner text-brand-600" /> Loading record…
            </div>
          ) : error ? (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          ) : record ? (
            <div className="space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Patient" value={record.patientName} />
                <Field
                  label="Prescription Code"
                  value={<span className="font-mono">{record.rxId}</span>}
                />
                <Field
                  label="Drug"
                  value={
                    <Link
                      to={`/prescription/${record.rxId}`}
                      className="text-brand-600 hover:underline dark:text-brand-400"
                    >
                      {record.drugName}
                    </Link>
                  }
                />
                <Field label="Setting" value={record.setting} />
                <Field label="Language" value={record.language} />
                <Field
                  label="Delivery Method"
                  value={
                    <span className={`chip ${METHOD_TONE[record.deliveryMethod]}`}>
                      {METHOD_LABEL[record.deliveryMethod]}
                    </span>
                  }
                />
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Information Provided
                </div>
                <p className="mt-2 rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 whitespace-pre-wrap dark:bg-slate-800/50 dark:text-slate-300">
                  {record.informationProvided}
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/50">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Pharmacist Signature
                </div>
                <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field label="Dispensed By" value={`PharmD ${record.pharmacistName}`} />
                  <Field
                    label="Licence"
                    value={<span className="font-mono">{record.pharmacistLicense}</span>}
                  />
                  <Field label="Dispensed At" value={formatTimestamp(record.dispensedAt)} />
                  <Field
                    label="Signature"
                    value={
                      record.signatureConfirmed ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                          <CheckCircleIcon width={14} height={14} /> Confirmed
                        </span>
                      ) : (
                        <span className="text-amber-700 dark:text-amber-400">Pending</span>
                      )
                    }
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-6 py-3 dark:border-slate-800">
          <button
            type="button"
            onClick={onClose}
            disabled={exporting}
            className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
          >
            Close
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={!record || exporting}
            className="btn btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {exporting ? <span className="spinner" /> : <DownloadIcon />}
            {exporting ? "Exporting…" : "Export Record"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-1 text-sm text-slate-900 dark:text-slate-100">{value}</div>
    </div>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
