import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  XIcon,
  BarcodeIcon,
  CheckCircleIcon,
  AlertOctagonIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
  ChevronDownIcon,
  CheckIcon,
  PrinterIcon,
  AlertCircleIcon,
} from "./Icons";
import { useTranslation } from "react-i18next";
import { ApiError, approvePrescription } from "../lib/api";
import { hmvsVerify } from "../lib/hmvs";
import { useModalRegistration } from "../lib/keyboard";
import { HmvsSecureInput, type HmvsBlockReason } from "./HmvsSecureInput";

type WizardView =
  | "s1-idle"
  | "s1-verifying"
  | "s1-failed"
  | "s1-unavailable"
  | "s2-idle"
  | "s2-submitting"
  | "s2-success"
  | "s2-failure";

interface DispenseWizardProps {
  open: boolean;
  rxId: string;
  barcode: string;
  patientName: string;
  drugName: string;
  nhrn?: string;
  onClose: () => void;
  onDispensed: (status: string) => void;
}

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg
      className="animate-spin"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function StepDots({ step }: { step: 1 | 2 }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2 w-2 rounded-full transition-colors ${step >= 1 ? "bg-brand-600" : "bg-slate-300 dark:bg-slate-600"}`}
      />
      <span
        className={`h-1.5 w-6 rounded-full transition-colors ${step >= 2 ? "bg-brand-600" : "bg-slate-200 dark:bg-slate-700"}`}
      />
      <span
        className={`h-2 w-2 rounded-full transition-colors ${step >= 2 ? "bg-brand-600" : "bg-slate-300 dark:bg-slate-600"}`}
      />
      <span className="ml-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {t("dispense.stepIndicator", { step })}
      </span>
    </div>
  );
}

function SummaryRow({
  label,
  children,
  strong,
}: {
  label: string;
  children: React.ReactNode;
  strong?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <span className="text-[12.5px] text-slate-500 dark:text-slate-400">{label}</span>
      <span
        className={`text-right text-[13px] ${strong ? "font-bold text-slate-900 dark:text-slate-100" : "font-medium text-slate-800 dark:text-slate-200"}`}
      >
        {children}
      </span>
    </div>
  );
}

export function DispenseWizard({
  open,
  rxId,
  barcode,
  patientName,
  drugName,
  nhrn,
  onClose,
  onDispensed,
}: DispenseWizardProps) {
  const { t } = useTranslation();
  useModalRegistration(open);

  const titleId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const [view, setView] = useState<WizardView>("s1-idle");
  const [manual, setManual] = useState(false);
  const [payload, setPayload] = useState("");
  // Caps Lock / wrong-keyboard-layout guard for the scanned pack code (H1).
  const [hmvsBlock, setHmvsBlock] = useState<HmvsBlockReason>(null);
  const [scheme, setScheme] = useState<"GS1" | "PPN">("GS1");
  // Controlled state for manual-entry fields
  const [manualProductCode, setManualProductCode] = useState("");
  const [manualSerial, setManualSerial] = useState("");
  const [manualBatch, setManualBatch] = useState("");
  const [manualExpiry, setManualExpiry] = useState("");
  const [counsel, setCounsel] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [dispenseError, setDispenseError] = useState<string | null>(null);
  const [dispenseErrorDetail, setDispenseErrorDetail] = useState<string | null>(null);
  const [executionNo, setExecutionNo] = useState<string | null>(null);
  const [packVerified, setPackVerified] = useState(false);

  // Reset internal state when wizard opens
  useEffect(() => {
    if (!open) return;
    setView("s1-idle");
    setManual(false);
    setPayload("");
    setHmvsBlock(null);
    setScheme("GS1");
    setManualProductCode("");
    setManualSerial("");
    setManualBatch("");
    setManualExpiry("");
    setCounsel(false);
    setShowDetails(false);
    setVerifyError(null);
    setDispenseError(null);
    setDispenseErrorDetail(null);
    setExecutionNo(null);
    setPackVerified(false);
  }, [open]);

  // Focus the payload input when Step 1 is idle
  useEffect(() => {
    if (open && view === "s1-idle" && !manual) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open, view, manual]);

  // Escape key handler
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && view !== "s2-submitting") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, view, onClose]);

  async function handleVerify() {
    // Defence in depth: never verify a scanned code that the H1 guard flagged
    // (Caps Lock / wrong layout), even if a caller bypasses the disabled button.
    if (!manual && hmvsBlock !== null) return;
    setView("s1-verifying");
    setVerifyError(null);
    // In manual mode, assemble GS1/PPN fields into the payload string sent to hmvsVerify
    const effectivePayload = manual
      ? `${scheme}:${manualProductCode}:${manualSerial}:${manualBatch}:${manualExpiry}`
      : payload;
    try {
      await hmvsVerify(effectivePayload);
      setPackVerified(true);
      setView("s2-idle");
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) {
        setView("s1-unavailable");
      } else if (e instanceof ApiError) {
        setVerifyError(e.message);
        setView("s1-failed");
      } else {
        setVerifyError(t("dispense.verifyGenericError"));
        setView("s1-failed");
      }
    }
  }

  function proceedWithoutVerification() {
    setPackVerified(false);
    setView("s2-idle");
  }

  async function handleConfirmDispense() {
    setView("s2-submitting");
    setDispenseError(null);
    setDispenseErrorDetail(null);
    try {
      const result = await approvePrescription(rxId);
      // TODO(H6): once the /pharmapi/hmvs proxy lands, decommission the verified
      // pack here on success via hmvsDecommission(packPayload, reason) — the pack
      // scanned in step 1 must be retained from handleVerify and passed in. Until
      // then the wizard records approval only; the pack is NOT decommissioned,
      // despite the step-2 copy. See docs/hmvs-scope.md.
      const execNo = result.executionNo ?? null;
      setExecutionNo(execNo);
      setView("s2-success");
      onDispensed(result.status);
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) {
        setDispenseError(t("dispense.dispenseNotWired"));
        setDispenseErrorDetail(
          `rxId: ${rxId}\nstatus: 501 Not Implemented\n${t("dispense.diagnosticMockOnly")}`,
        );
      } else if (e instanceof ApiError) {
        setDispenseError(t("dispense.dispenseRejected", { message: e.message }));
        setDispenseErrorDetail(`rxId: ${rxId}\nstatus: ${e.status}\n${e.message}`);
      } else {
        setDispenseError(t("dispense.dispenseGenericError"));
        setDispenseErrorDetail(null);
      }
      setView("s2-failure");
    }
  }

  if (!open) return null;

  const step: 1 | 2 = view.startsWith("s1") ? 1 : 2;
  const success = view === "s2-success";

  return createPortal(
    <div
      className="fixed inset-0 z-50 animate-fade-in bg-slate-900/40"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && view !== "s2-submitting") onClose();
      }}
    >
      <div className="flex h-full items-center justify-center p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="w-full max-w-[560px] animate-modal-in overflow-hidden rounded-2xl bg-white dark:bg-slate-900 shadow-modal"
        >
          {/* ── modal header (steps 1 & 2, not success) ── */}
          {!success && (
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4">
              <StepDots step={step} />
              <button
                type="button"
                onClick={onClose}
                disabled={view === "s2-submitting"}
                aria-label={t("dispense.cancel")}
                className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300 disabled:opacity-40"
              >
                <XIcon width={18} height={18} />
              </button>
            </div>
          )}

          {/* ══════════════ STEP 1 ══════════════ */}
          {step === 1 && (
            <div className="px-6 py-6">
              <h2 id={titleId} className="text-[18px] font-bold text-slate-900 dark:text-slate-100">
                {t("dispense.step1Title")}
              </h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                {t("dispense.step1DescBefore")}{" "}
                <span className="font-semibold text-slate-700 dark:text-slate-300">{drugName}</span>{" "}
                {t("dispense.step1DescAfter")}
              </p>

              {nhrn && (
                <div className="mt-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-4 py-1.5">
                  <SummaryRow label={t("dispense.nhrnLabel")}>
                    <span className="mono">{nhrn}</span>
                  </SummaryRow>
                </div>
              )}

              {/* s1-unavailable — stub not wired */}
              {view === "s1-unavailable" && (
                <div className="mt-5 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-4">
                  <div className="flex items-start gap-3">
                    <AlertCircleIcon
                      width={20}
                      height={20}
                      className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400"
                    />
                    <div className="flex-1">
                      <div className="text-[13.5px] font-bold text-amber-800 dark:text-amber-400">
                        {t("dispense.unavailableTitle")}
                      </div>
                      <p className="mt-1 text-[12.5px] text-amber-700/90 dark:text-amber-400/90">
                        {t("dispense.unavailableBody")}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* s1-failed — pack already dispensed / error */}
              {view === "s1-failed" && (
                <div className="mt-5 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-5">
                  <div className="flex items-start gap-3">
                    <AlertOctagonIcon
                      width={22}
                      height={22}
                      className="shrink-0 text-red-600 dark:text-red-400"
                    />
                    <div className="flex-1">
                      <div className="text-[14px] font-bold text-red-800 dark:text-red-400">
                        {verifyError ?? t("dispense.verifyFailedTitle")}
                      </div>
                      <p className="mt-1 text-[12.5px] text-red-700/90 dark:text-red-400/90">
                        {t("dispense.verifyFailedBody")}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* scan / entry area — shown unless failed or unavailable with a different layout */}
              {view !== "s1-failed" && view !== "s1-unavailable" && (
                <>
                  {!manual ? (
                    <div className="mt-5">
                      <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 py-9 text-center">
                        {view === "s1-verifying" ? (
                          <>
                            <span className="text-brand-600 dark:text-brand-400">
                              <Spinner size={30} />
                            </span>
                            <p className="mt-3 text-[13px] font-medium text-slate-600 dark:text-slate-300">
                              {t("dispense.queryingHmvs")}
                            </p>
                          </>
                        ) : (
                          <>
                            <span className="text-slate-400 dark:text-slate-500">
                              <BarcodeIcon width={38} height={38} />
                            </span>
                            <p className="mt-2.5 text-[13px] font-medium text-slate-500 dark:text-slate-400">
                              {t("dispense.scanPrompt")}
                            </p>
                          </>
                        )}
                      </div>
                      <div className="mt-3">
                        <HmvsSecureInput
                          inputRef={inputRef}
                          value={payload}
                          onChange={setPayload}
                          onBlock={setHmvsBlock}
                          disabled={view === "s1-verifying"}
                          onKeyDown={(e) => {
                            if (
                              e.key === "Enter" &&
                              payload.trim() &&
                              view === "s1-idle" &&
                              hmvsBlock === null
                            )
                              handleVerify();
                          }}
                          placeholder="01057001234567892..."
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => setManual(true)}
                        disabled={view === "s1-verifying"}
                        className="mt-2.5 text-[12.5px] font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 disabled:opacity-50"
                      >
                        {t("dispense.skipManualEntry")}
                      </button>
                    </div>
                  ) : (
                    <div className="mt-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
                      <div className="mb-3 flex items-center justify-between">
                        <span className="text-[12px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          {t("dispense.manualEntry")}
                        </span>
                        <div className="flex items-center gap-1 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-0.5">
                          {(["GS1", "PPN"] as const).map((s) => (
                            <button
                              key={s}
                              type="button"
                              onClick={() => setScheme(s)}
                              className={`rounded-full px-2.5 py-1 text-[11.5px] font-semibold transition-colors ${scheme === s ? "bg-brand-600 text-white" : "text-slate-500 dark:text-slate-400"}`}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2.5">
                        {(
                          [
                            [
                              t("dispense.productCode"),
                              "05700123456789",
                              manualProductCode,
                              setManualProductCode,
                            ],
                            [t("dispense.serialNumber"), "9d8X7p17", manualSerial, setManualSerial],
                            [t("dispense.batch"), "B-4471", manualBatch, setManualBatch],
                            [t("dispense.expiry"), "270531", manualExpiry, setManualExpiry],
                          ] as [string, string, string, (v: string) => void][]
                        ).map(([label, ph, val, setter]) => (
                          <label key={label} className="block">
                            <span className="mb-1 block text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                              {label}
                            </span>
                            <input
                              value={val}
                              onChange={(e) => setter(e.target.value)}
                              placeholder={ph}
                              className="mono w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 dark:text-slate-100 px-3 py-2 text-[12.5px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                            />
                          </label>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={() => setManual(false)}
                        className="mt-3 text-[12px] font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                      >
                        {t("dispense.backToScan")}
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* footer */}
              <div className="mt-6 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  {t("dispense.cancel")}
                </button>

                {view === "s1-failed" ? (
                  <button
                    type="button"
                    onClick={() => {
                      setView("s1-idle");
                      setPayload("");
                      setHmvsBlock(null);
                      setShowDetails(false);
                    }}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700"
                  >
                    {t("dispense.scanAnotherPack")}
                  </button>
                ) : view === "s1-unavailable" ? (
                  <button
                    type="button"
                    onClick={proceedWithoutVerification}
                    className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700"
                  >
                    {t("dispense.proceedToConfirm")} <ChevronRightIcon width={15} height={15} />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleVerify}
                    disabled={
                      view === "s1-verifying" ||
                      (!manual && !payload.trim()) ||
                      (!manual && hmvsBlock !== null) ||
                      (manual && !manualProductCode.trim())
                    }
                    className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:bg-brand-600/70"
                  >
                    {view === "s1-verifying" ? (
                      <>
                        <Spinner size={15} /> {t("dispense.verifying")}
                      </>
                    ) : (
                      <>
                        {t("dispense.verifyPack")} <ChevronRightIcon width={15} height={15} />
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* ══════════════ STEP 2 (idle / submitting / failure) ══════════════ */}
          {step === 2 && !success && (
            <div className="px-6 py-6">
              <h2 id={titleId} className="text-[18px] font-bold text-slate-900 dark:text-slate-100">
                {t("dispense.step2Title")}
              </h2>

              {packVerified ? (
                <div className="mt-4 flex items-center gap-2.5 rounded-lg border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 px-3.5 py-3 text-[13px] font-medium text-emerald-700 dark:text-emerald-400">
                  <CheckCircleIcon width={18} height={18} /> {t("dispense.packVerifiedBanner")}
                </div>
              ) : (
                <div className="mt-4 flex items-center gap-2.5 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3.5 py-3 text-[13px] font-medium text-amber-700 dark:text-amber-400">
                  <AlertCircleIcon width={18} height={18} /> {t("dispense.packSkippedBanner")}
                </div>
              )}

              <div className="mt-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-4 py-1.5">
                <SummaryRow label={t("dispense.patient")}>{patientName}</SummaryRow>
                <div className="border-t border-slate-200/70 dark:border-slate-800" />
                <SummaryRow label={t("dispense.medicine")}>{drugName}</SummaryRow>
                {nhrn && (
                  <>
                    <div className="border-t border-slate-200/70 dark:border-slate-800" />
                    <SummaryRow label={t("dispense.nhrnLabel")}>
                      <span className="mono">{nhrn}</span>
                    </SummaryRow>
                  </>
                )}
              </div>

              {!packVerified && (
                <p className="mt-2.5 text-[12px] text-slate-500 dark:text-slate-400">
                  {t("dispense.decommissionSkippedNote")}
                </p>
              )}
              {packVerified && (
                <p className="mt-2.5 text-[12px] text-slate-500 dark:text-slate-400">
                  {t("dispense.decommissionNote")}
                </p>
              )}

              {/* TODO: pass counsel to approvePrescription when API supports it */}
              <label className="mt-3 flex cursor-pointer items-center gap-2.5">
                <input
                  type="checkbox"
                  checked={counsel}
                  onChange={(e) => setCounsel(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 dark:border-slate-700 text-brand-600 focus:ring-brand-500"
                />
                <span className="text-[13px] text-slate-600 dark:text-slate-300">
                  {t("dispense.generateCounseling")}
                </span>
              </label>

              {view === "s2-failure" && dispenseError && (
                <div className="mt-4 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-4">
                  <div className="flex items-start gap-2.5">
                    <AlertOctagonIcon
                      width={18}
                      height={18}
                      className="mt-0.5 shrink-0 text-red-600 dark:text-red-400"
                    />
                    <div className="flex-1">
                      <div className="text-[13px] font-bold text-red-800 dark:text-red-400">
                        {dispenseError}
                      </div>
                      {dispenseErrorDetail && (
                        <>
                          <button
                            type="button"
                            onClick={() => setShowDetails((s) => !s)}
                            className="mt-1.5 flex items-center gap-0.5 text-[12px] font-semibold text-red-700 dark:text-red-400"
                          >
                            <span
                              className={`transition-transform ${showDetails ? "rotate-180" : ""}`}
                            >
                              <ChevronDownIcon width={13} height={13} />
                            </span>{" "}
                            {t("dispense.showDiagnostic")}
                          </button>
                          {showDetails && (
                            <pre className="mono mt-2 whitespace-pre-wrap rounded-lg bg-red-100/60 dark:bg-red-500/10 p-3 text-[11px] leading-relaxed text-red-800 dark:text-red-300">
                              {dispenseErrorDetail}
                            </pre>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="mt-6 flex items-center justify-between gap-2.5">
                <button
                  type="button"
                  onClick={() => {
                    setView("s1-idle");
                    setShowDetails(false);
                  }}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  <ChevronLeftIcon width={15} height={15} /> {t("dispense.back")}
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDispense}
                  disabled={view === "s2-submitting"}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:bg-brand-600/70"
                >
                  {view === "s2-submitting" ? (
                    <>
                      <Spinner size={15} /> {t("dispense.submittingToHdyka")}
                    </>
                  ) : view === "s2-failure" ? (
                    t("dispense.retryDispense")
                  ) : (
                    t("dispense.confirmDispense")
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ══════════════ SUCCESS ══════════════ */}
          {success && (
            <div className="px-6 py-10 text-center">
              <div className="mx-auto flex h-16 w-16 animate-pop items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <CheckIcon width={36} height={36} strokeWidth={2.5} />
              </div>
              <h2
                id={titleId}
                className="mt-5 text-[20px] font-bold text-slate-900 dark:text-slate-100"
              >
                {t("dispense.successTitle")}
              </h2>
              <p className="mt-1.5 text-[13px] text-slate-500 dark:text-slate-400">
                {packVerified
                  ? t("dispense.successBodyVerified")
                  : t("dispense.successBodySkipped")}
              </p>
              <div className="mx-auto mt-5 max-w-[360px] rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-4 py-1.5 text-left">
                {executionNo && (
                  <>
                    <SummaryRow label={t("dispense.executionNo")}>
                      <span className="mono">{executionNo}</span>
                    </SummaryRow>
                    <div className="border-t border-slate-200/70 dark:border-slate-800" />
                  </>
                )}
                <SummaryRow label={t("dispense.prescription")}>
                  <span className="mono">{barcode}</span>
                </SummaryRow>
              </div>
              <div className="mt-6 flex items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  <PrinterIcon width={15} height={15} /> {t("dispense.printReceipt")}
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg bg-brand-600 px-5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700"
                >
                  {t("dispense.backToCounter")}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
