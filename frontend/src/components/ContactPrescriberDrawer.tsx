import { useEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { PhoneIcon, MailIcon, SendIcon, XIcon, CheckCircleIcon } from "./Icons";
import { ApiError, recordPrescriberContact } from "../lib/api";
import { useToast } from "./Toast";
import { useModalRegistration } from "../lib/keyboard";
import type { Prescriber } from "../types";

interface ContactPrescriberDrawerProps {
  open: boolean;
  rxId: string;
  patientName: string;
  prescriber: Prescriber;
  onClose: () => void;
}

// ΗΔΥΚΑ gives us only the prescriber's NAME — no phone/email/message channel.
// So this drawer shows whatever contact detail exists (never a dead link), and
// its one action is to RECORD a contact note to the documentation log. There is
// no automated delivery, and we never pretend there is.
export function ContactPrescriberDrawer({
  open,
  rxId,
  patientName,
  prescriber,
  onClose,
}: ContactPrescriberDrawerProps) {
  useModalRegistration(open);
  const { t } = useTranslation();
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState(false);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    if (!open) return;
    setBody("");
    setError(null);
    setRecorded(false);
    const id = setTimeout(() => closeBtnRef.current?.focus(), 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(id);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, rxId, saving, onClose]);

  if (!open) return null;

  const phone = prescriber.contact?.trim();
  const email = prescriber.email?.trim();
  const licence = prescriber.licenceId?.trim();
  const specialty = prescriber.specialty?.trim();
  const hasChannel = Boolean(phone || email);
  const mailtoHref = email
    ? `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(
        t("contact.emailSubject", { rxId, patientName }),
      )}`
    : undefined;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving || !body.trim()) {
      if (!body.trim()) setError(t("contact.errEmpty"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await recordPrescriberContact(rxId, body.trim());
      setRecorded(true);
      setBody("");
      toast(t("contact.recordedToast"), "success");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("contact.errRecord"));
    } finally {
      setSaving(false);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-slate-900/40 animate-fade-in"
        onClick={() => {
          if (!saving) onClose();
        }}
        aria-hidden="true"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={t("contact.title")}
        className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white dark:bg-slate-900 shadow-cardLg animate-slide-in-right"
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 dark:border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {t("contact.title")}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              <span className="font-mono">{rxId}</span> — {patientName}
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
            aria-label={t("contact.closePanel")}
          >
            <XIcon />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          {/* Prescriber card — only render detail that ΗΔΥΚΑ actually provides */}
          <section className="border-b border-slate-200 dark:border-slate-800 px-5 py-4">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {prescriber.name || "—"}
              </div>
              {specialty && (
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{specialty}</div>
              )}
              {(licence || phone || email) && (
                <dl className="mt-3 space-y-2 text-[13px]">
                  {licence && (
                    <Field
                      label={t("contact.licenceId")}
                      value={<span className="font-mono">{licence}</span>}
                    />
                  )}
                  {phone && (
                    <Field
                      label={t("contact.phone")}
                      value={
                        <a
                          href={`tel:${phone}`}
                          className="text-brand-600 dark:text-brand-400 hover:underline"
                        >
                          {phone}
                        </a>
                      }
                    />
                  )}
                  {email && (
                    <Field
                      label={t("contact.email")}
                      value={
                        <a
                          href={mailtoHref}
                          className="text-brand-600 dark:text-brand-400 hover:underline"
                        >
                          {email}
                        </a>
                      }
                    />
                  )}
                </dl>
              )}
            </div>

            {/* Contact channels — shown only when ΗΔΥΚΑ gave us one */}
            {hasChannel ? (
              <div className="mt-4 grid grid-cols-2 gap-2">
                {phone && (
                  <a href={`tel:${phone}`} className="btn btn-outline justify-center">
                    <PhoneIcon /> {t("contact.call")}
                  </a>
                )}
                {mailtoHref && (
                  <a href={mailtoHref} className="btn btn-outline justify-center">
                    <MailIcon /> {t("contact.emailAction")}
                  </a>
                )}
              </div>
            ) : (
              <p className="mt-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3.5 py-2.5 text-[12.5px] leading-snug text-slate-500 dark:text-slate-400">
                {t("contact.noChannel")}
              </p>
            )}
          </section>

          {/* Record a contact note → documentation log */}
          <section className="px-5 py-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {t("contact.recordTitle")}
            </h3>
            <p className="mt-1 text-[12.5px] leading-snug text-slate-500 dark:text-slate-400">
              {t("contact.recordHint")}
            </p>

            {recorded && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-2.5 text-[13px] text-emerald-700 dark:text-emerald-400">
                <CheckCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
                <span>{t("contact.recordedNote")}</span>
              </div>
            )}
          </section>
        </div>

        <form
          onSubmit={onSubmit}
          className="border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-5 py-4"
        >
          {error && (
            <div className="mb-2 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-xs text-red-800 dark:text-red-400">
              {error}
            </div>
          )}
          <label htmlFor="contact-note" className="sr-only">
            {t("contact.recordTitle")}
          </label>
          <textarea
            id="contact-note"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={t("contact.recordPlaceholder", { name: prescriber.name })}
            className="w-full min-h-[88px] resize-vertical rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 dark:text-slate-100 px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          />
          <div className="mt-2 flex justify-end">
            <button
              type="submit"
              disabled={saving || !body.trim()}
              className="btn btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {saving ? <span className="spinner" /> : <SendIcon />}
              {saving ? t("contact.recording") : t("contact.recordAction")}
            </button>
          </div>
        </form>
      </aside>
    </div>,
    document.body,
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="text-right text-sm text-slate-900 dark:text-slate-100">{value}</dd>
    </div>
  );
}
