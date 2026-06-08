import { useState } from "react";
import { useTranslation } from "react-i18next";
import { HmvsSecureInput, type HmvsBlockReason } from "../components/HmvsSecureInput";
import { CheckCircleIcon, ShieldIcon } from "../components/Icons";

/**
 * Isolated demo surface for the H1 HMVS-input safeguards (Caps Lock + wrong
 * keyboard-layout detection). Mock data only — no patient data — so it can be
 * screen-recorded for the HMVO Gate-2 deliverable without exposing PII. Not in
 * the sidebar nav; reachable at /hmvs-check.
 */
export function HmvsCheck() {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [blockReason, setBlockReason] = useState<HmvsBlockReason>(null);
  const [accepted, setAccepted] = useState(false);

  const blocked = blockReason !== null;
  const canSubmit = !blocked && value.trim().length > 0;

  return (
    <div className="mx-auto max-w-xl px-4 py-10 sm:px-6">
      <header className="mb-6 flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white">
          <ShieldIcon width={20} height={20} />
        </span>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {t("hmvsCheck.title")}
          </h1>
          <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
            {t("hmvsCheck.subtitle")}
          </p>
        </div>
      </header>

      <div className="card p-6">
        <HmvsSecureInput
          value={value}
          onChange={(v) => {
            setValue(v);
            setAccepted(false);
          }}
          onBlock={setBlockReason}
          label={t("hmvsCheck.inputLabel")}
          placeholder="01057001234567892..."
        />

        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => setAccepted(true)}
          className={`btn mt-4 w-full justify-center ${
            canSubmit
              ? "btn-primary"
              : "cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
          }`}
        >
          {t("hmvsCheck.submit")}
        </button>

        {accepted && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-[13px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400">
            <CheckCircleIcon width={16} height={16} className="shrink-0" />
            {t("hmvsCheck.accepted")}
          </div>
        )}

        <p className="mt-4 text-[12px] leading-relaxed text-slate-400 dark:text-slate-500">
          {t("hmvsCheck.demoNote")}
        </p>
      </div>
    </div>
  );
}
