import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { FlagIcon } from "./Icons";
import {
  ApiError,
  recordPrescriberContact,
  patchPrescription,
  type DiscrepancyType,
} from "../lib/api";
import { useToast } from "./Toast";
import { useModalRegistration } from "../lib/keyboard";

interface FlagDiscrepancyModalProps {
  rxId: string;
  open: boolean;
  onClose: () => void;
  onFlagged?: (status: string) => void;
}

const DISCREPANCY_OPTIONS: { value: DiscrepancyType; labelKey: string }[] = [
  { value: "dose_error", labelKey: "flag.typeDoseError" },
  { value: "drug_drug_interaction", labelKey: "flag.typeDrugDrugInteraction" },
  { value: "missing_info", labelKey: "flag.typeMissingInfo" },
  { value: "suspected_forgery", labelKey: "flag.typeSuspectedForgery" },
  { value: "other", labelKey: "flag.typeOther" },
];

const TYPE_LABEL_KEY: Record<DiscrepancyType, string> = Object.fromEntries(
  DISCREPANCY_OPTIONS.map((o) => [o.value, o.labelKey]),
) as Record<DiscrepancyType, string>;

export function FlagDiscrepancyModal({
  rxId,
  open,
  onClose,
  onFlagged,
}: FlagDiscrepancyModalProps) {
  useModalRegistration(open);
  const { t } = useTranslation();
  const titleId = useId();
  const [discrepancyType, setDiscrepancyType] = useState<DiscrepancyType | "">("");
  const [notes, setNotes] = useState("");
  const [notifyPhysicianFlag, setNotifyPhysicianFlag] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { toast } = useToast();
  const firstFieldRef = useRef<HTMLSelectElement | null>(null);

  // Reset and focus first field on open.
  useEffect(() => {
    if (!open) return;
    setDiscrepancyType("");
    setNotes("");
    setNotifyPhysicianFlag(false);
    setErr(null);
    setSubmitting(false);
    const t = setTimeout(() => firstFieldRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setErr(null);
    if (!discrepancyType) {
      setErr(t("flag.errSelectType"));
      return;
    }
    if (!notes.trim()) {
      setErr(t("flag.errDescribe"));
      return;
    }
    setSubmitting(true);
    try {
      const result = await patchPrescription(rxId, {
        status: "flagged",
        discrepancy_type: discrepancyType as DiscrepancyType,
        notes: notes.trim(),
        notify_physician: notifyPhysicianFlag,
      });

      if (notifyPhysicianFlag) {
        // Best-effort — don't fail the flagging if the contact record fails.
        try {
          await recordPrescriberContact(
            rxId,
            t("flag.notifyMessage", {
              rxId,
              type: t(TYPE_LABEL_KEY[discrepancyType as DiscrepancyType]),
              notes: notes.trim(),
            }),
          );
        } catch (e) {
          toast(
            e instanceof ApiError
              ? t("flag.notifyFailedReason", { reason: e.message })
              : t("flag.notifyFailed"),
            "warn",
          );
        }
      }

      toast(t("flag.flaggedSuccess", { rxId }), "success");
      onFlagged?.(result.status);
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("flag.errCouldNotFlag"));
    } finally {
      setSubmitting(false);
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 animate-alert-in"
      onMouseDown={(e) => {
        // Click on backdrop closes; clicks inside dialog don't bubble here.
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-2xl bg-white shadow-cardLg dark:bg-slate-900"
      >
        <div className="flex items-start gap-3 border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
            <FlagIcon />
          </div>
          <div className="flex-1">
            <h2 id={titleId} className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {t("flag.title")}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              <span className="font-mono">{rxId}</span> — {t("flag.subtitle")}
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="px-6 py-5">
          {err && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
              {err}
            </div>
          )}

          <label
            htmlFor="discrepancyType"
            className="block text-[13px] font-medium text-slate-600 dark:text-slate-300"
          >
            {t("flag.discrepancyType")}
          </label>
          <select
            id="discrepancyType"
            ref={firstFieldRef}
            value={discrepancyType}
            onChange={(e) => setDiscrepancyType(e.target.value as DiscrepancyType | "")}
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          >
            <option value="" disabled>
              {t("flag.selectType")}
            </option>
            {DISCREPANCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>

          <label
            htmlFor="notes"
            className="mt-4 block text-[13px] font-medium text-slate-600 dark:text-slate-300"
          >
            {t("flag.notes")}
          </label>
          <textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={t("flag.notesPlaceholder")}
            className="mt-1.5 w-full min-h-[110px] resize-vertical rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />

          <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-[13px] text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={notifyPhysicianFlag}
              onChange={(e) => setNotifyPhysicianFlag(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-100 dark:border-slate-700"
            />
            <span>{t("flag.notifyPhysician")}</span>
          </label>

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {t("flag.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn btn-amber disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitting ? <span className="spinner" /> : <FlagIcon />}
              {submitting ? t("flag.submitting") : t("flag.submitFlag")}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
