import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { CheckIcon } from "./Icons";
import { useModalRegistration } from "../lib/keyboard";

interface ApproveConfirmModalProps {
  open: boolean;
  rxId: string;
  patientName: string;
  drugName: string;
  dose: string;
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export function ApproveConfirmModal({
  open,
  rxId,
  patientName,
  drugName,
  dose,
  submitting,
  error,
  onClose,
  onConfirm,
}: ApproveConfirmModalProps) {
  useModalRegistration(open);
  const titleId = useId();
  const [confirmed, setConfirmed] = useState(false);
  const checkboxRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setConfirmed(false);
    const t = setTimeout(() => checkboxRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!confirmed || submitting) return;
    onConfirm();
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 animate-alert-in"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-2xl bg-white shadow-cardLg"
      >
        <div className="flex items-start gap-3 border-b border-slate-200 px-6 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
            <CheckIcon />
          </div>
          <div className="flex-1">
            <h2 id={titleId} className="text-base font-semibold text-slate-900">
              Confirm Prescription Approval
            </h2>
            <p className="text-xs text-slate-500">
              <span className="font-mono">{rxId}</span> — once approved, the prescription is
              recorded.
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="px-6 py-5">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <Row label="Patient" value={patientName} />
            <Row label="Drug" value={drugName} />
            <Row label="Dose" value={dose} last />
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </div>
          )}

          <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-[13px] text-slate-700">
            <input
              ref={checkboxRef}
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-100"
            />
            <span>I confirm I have reviewed all safety checks and patient information</span>
          </label>

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!confirmed || submitting}
              className="btn btn-success disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitting ? <span className="spinner" /> : <CheckIcon />}
              {submitting ? "Approving…" : "Confirm Approval"}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between ${last ? "" : "border-b border-slate-200 pb-2 mb-2"}`}
    >
      <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
      <span className="text-sm font-semibold text-slate-900">{value}</span>
    </div>
  );
}
