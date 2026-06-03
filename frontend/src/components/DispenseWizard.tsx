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
import { ApiError, approvePrescription, verifyPack } from "../lib/api";
import { useModalRegistration } from "../lib/keyboard";

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
  participation?: string;
  patientPays?: string;
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
  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2 w-2 rounded-full transition-colors ${step >= 1 ? "bg-brand-600" : "bg-slate-300"}`}
      />
      <span
        className={`h-1.5 w-6 rounded-full transition-colors ${step >= 2 ? "bg-brand-600" : "bg-slate-200"}`}
      />
      <span
        className={`h-2 w-2 rounded-full transition-colors ${step >= 2 ? "bg-brand-600" : "bg-slate-300"}`}
      />
      <span className="ml-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Step {step}/2
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
      <span className="text-[12.5px] text-slate-500">{label}</span>
      <span
        className={`text-right text-[13px] ${strong ? "font-bold text-slate-900" : "font-medium text-slate-800"}`}
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
  participation,
  patientPays,
  onClose,
  onDispensed,
}: DispenseWizardProps) {
  useModalRegistration(open);

  const titleId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const [view, setView] = useState<WizardView>("s1-idle");
  const [manual, setManual] = useState(false);
  const [payload, setPayload] = useState("");
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
    setView("s1-verifying");
    setVerifyError(null);
    // In manual mode, assemble GS1/PPN fields into the payload string sent to verifyPack
    const effectivePayload = manual
      ? `${scheme}:${manualProductCode}:${manualSerial}:${manualBatch}:${manualExpiry}`
      : payload;
    try {
      await verifyPack(effectivePayload);
      setPackVerified(true);
      setView("s2-idle");
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) {
        setView("s1-unavailable");
      } else if (e instanceof ApiError) {
        setVerifyError(e.message);
        setView("s1-failed");
      } else {
        setVerifyError("Verification failed. Please try again.");
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
      // Extract execution number from response if available
      const execNo = (result as { executionNo?: string }).executionNo ?? null;
      setExecutionNo(execNo);
      setView("s2-success");
      onDispensed(result.status);
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) {
        setDispenseError(
          "Live dispense not yet wired — ΗΔΥΚΑ execution endpoint returns HTTP 501.",
        );
        setDispenseErrorDetail(
          `rxId: ${rxId}\nstatus: 501 Not Implemented\nLive dispense is mock-only today.`,
        );
      } else if (e instanceof ApiError) {
        setDispenseError(`ΗΔΥΚΑ rejected the dispense: ${e.message}`);
        setDispenseErrorDetail(`rxId: ${rxId}\nstatus: ${e.status}\n${e.message}`);
      } else {
        setDispenseError("Dispense failed. Please try again.");
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
          className="w-full max-w-[560px] animate-modal-in overflow-hidden rounded-2xl bg-white shadow-modal"
        >
          {/* ── modal header (steps 1 & 2, not success) ── */}
          {!success && (
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <StepDots step={step} />
              <button
                type="button"
                onClick={onClose}
                disabled={view === "s2-submitting"}
                aria-label="Cancel"
                className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 disabled:opacity-40"
              >
                <XIcon width={18} height={18} />
              </button>
            </div>
          )}

          {/* ══════════════ STEP 1 ══════════════ */}
          {step === 1 && (
            <div className="px-6 py-6">
              <h2 id={titleId} className="text-[18px] font-bold text-slate-900">
                Verify medicine pack
              </h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
                Scan the DataMatrix on the back of the{" "}
                <span className="font-semibold text-slate-700">{drugName}</span> box. This confirms
                the pack is genuine and decommissions it from the EU FMD registry.
              </p>

              {/* s1-unavailable — stub not wired */}
              {view === "s1-unavailable" && (
                <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <div className="flex items-start gap-3">
                    <AlertCircleIcon
                      width={20}
                      height={20}
                      className="mt-0.5 shrink-0 text-amber-600"
                    />
                    <div className="flex-1">
                      <div className="text-[13.5px] font-bold text-amber-800">
                        Pack verification not yet available
                      </div>
                      <p className="mt-1 text-[12.5px] text-amber-700/90">
                        The HMVS/FMD verification endpoint is not yet wired. You may proceed to
                        dispense approval only — the pack will not be decommissioned from the EU FMD
                        registry automatically.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* s1-failed — pack already dispensed / error */}
              {view === "s1-failed" && (
                <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-5">
                  <div className="flex items-start gap-3">
                    <AlertOctagonIcon width={22} height={22} className="shrink-0 text-red-600" />
                    <div className="flex-1">
                      <div className="text-[14px] font-bold text-red-800">
                        {verifyError ?? "Pack verification failed"}
                      </div>
                      <p className="mt-1 text-[12.5px] text-red-700/90">
                        Use a different pack or contact your HMVS administrator.
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
                      <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 py-9 text-center">
                        {view === "s1-verifying" ? (
                          <>
                            <span className="text-brand-600">
                              <Spinner size={30} />
                            </span>
                            <p className="mt-3 text-[13px] font-medium text-slate-600">
                              Querying the HMVS registry…
                            </p>
                          </>
                        ) : (
                          <>
                            <span className="text-slate-400">
                              <BarcodeIcon width={38} height={38} />
                            </span>
                            <p className="mt-2.5 text-[13px] font-medium text-slate-500">
                              Scan or type the DataMatrix payload
                            </p>
                          </>
                        )}
                      </div>
                      <input
                        ref={inputRef}
                        value={payload}
                        onChange={(e) => setPayload(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && payload.trim() && view === "s1-idle")
                            handleVerify();
                        }}
                        disabled={view === "s1-verifying"}
                        placeholder="01057001234567892..."
                        className="mono mt-3 w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-[13px] text-slate-900 outline-none placeholder:font-sans placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50"
                      />
                      <button
                        type="button"
                        onClick={() => setManual(true)}
                        disabled={view === "s1-verifying"}
                        className="mt-2.5 text-[12.5px] font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50"
                      >
                        Skip — manual entry
                      </button>
                    </div>
                  ) : (
                    <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="mb-3 flex items-center justify-between">
                        <span className="text-[12px] font-bold uppercase tracking-wide text-slate-500">
                          Manual entry
                        </span>
                        <div className="flex items-center gap-1 rounded-full border border-slate-200 bg-white p-0.5">
                          {(["GS1", "PPN"] as const).map((s) => (
                            <button
                              key={s}
                              type="button"
                              onClick={() => setScheme(s)}
                              className={`rounded-full px-2.5 py-1 text-[11.5px] font-semibold transition-colors ${scheme === s ? "bg-brand-600 text-white" : "text-slate-500"}`}
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
                              "Product code",
                              "05700123456789",
                              manualProductCode,
                              setManualProductCode,
                            ],
                            ["Serial number", "9d8X7p17", manualSerial, setManualSerial],
                            ["Batch", "B-4471", manualBatch, setManualBatch],
                            ["Expiry (YYMMDD)", "270531", manualExpiry, setManualExpiry],
                          ] as [string, string, string, (v: string) => void][]
                        ).map(([label, ph, val, setter]) => (
                          <label key={label} className="block">
                            <span className="mb-1 block text-[11px] font-semibold text-slate-500">
                              {label}
                            </span>
                            <input
                              value={val}
                              onChange={(e) => setter(e.target.value)}
                              placeholder={ph}
                              className="mono w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12.5px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                            />
                          </label>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={() => setManual(false)}
                        className="mt-3 text-[12px] font-medium text-slate-500 hover:text-slate-700"
                      >
                        ← Back to scan
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
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 transition-colors hover:bg-slate-50"
                >
                  Cancel
                </button>

                {view === "s1-failed" ? (
                  <button
                    type="button"
                    onClick={() => {
                      setView("s1-idle");
                      setPayload("");
                      setShowDetails(false);
                    }}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700"
                  >
                    Scan another pack
                  </button>
                ) : view === "s1-unavailable" ? (
                  <button
                    type="button"
                    onClick={proceedWithoutVerification}
                    className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700"
                  >
                    Proceed to confirm <ChevronRightIcon width={15} height={15} />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleVerify}
                    disabled={
                      view === "s1-verifying" ||
                      (!manual && !payload.trim()) ||
                      (manual && !manualProductCode.trim())
                    }
                    className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:bg-brand-600/70"
                  >
                    {view === "s1-verifying" ? (
                      <>
                        <Spinner size={15} /> Verifying…
                      </>
                    ) : (
                      <>
                        Verify pack <ChevronRightIcon width={15} height={15} />
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
              <h2 id={titleId} className="text-[18px] font-bold text-slate-900">
                Confirm dispense
              </h2>

              {packVerified ? (
                <div className="mt-4 flex items-center gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-[13px] font-medium text-emerald-700">
                  <CheckCircleIcon width={18} height={18} /> Pack verified — Active in the HMVS
                  registry
                </div>
              ) : (
                <div className="mt-4 flex items-center gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-[13px] font-medium text-amber-700">
                  <AlertCircleIcon width={18} height={18} /> Pack verification skipped — proceeding
                  on approval only
                </div>
              )}

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-1.5">
                <SummaryRow label="Patient">{patientName}</SummaryRow>
                <div className="border-t border-slate-200/70" />
                <SummaryRow label="Medicine">{drugName}</SummaryRow>
                {patientPays && (
                  <>
                    <div className="border-t border-slate-200/70" />
                    <SummaryRow
                      label={`Patient pays${participation ? ` (${participation} participation)` : ""}`}
                      strong
                    >
                      {patientPays}
                    </SummaryRow>
                  </>
                )}
              </div>

              {!packVerified && (
                <p className="mt-2.5 text-[12px] text-slate-500">
                  Pack decommission from the FMD registry will not occur automatically.
                </p>
              )}
              {packVerified && (
                <p className="mt-2.5 text-[12px] text-slate-500">
                  The pack will be decommissioned from the FMD registry on confirm.
                </p>
              )}

              <label className="mt-3 flex cursor-pointer items-center gap-2.5">
                <input
                  type="checkbox"
                  checked={counsel}
                  onChange={(e) => setCounsel(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <span className="text-[13px] text-slate-600">
                  Generate counseling instructions after dispense
                </span>
              </label>

              {view === "s2-failure" && dispenseError && (
                <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4">
                  <div className="flex items-start gap-2.5">
                    <AlertOctagonIcon
                      width={18}
                      height={18}
                      className="mt-0.5 shrink-0 text-red-600"
                    />
                    <div className="flex-1">
                      <div className="text-[13px] font-bold text-red-800">{dispenseError}</div>
                      {dispenseErrorDetail && (
                        <>
                          <button
                            type="button"
                            onClick={() => setShowDetails((s) => !s)}
                            className="mt-1.5 flex items-center gap-0.5 text-[12px] font-semibold text-red-700"
                          >
                            <span
                              className={`transition-transform ${showDetails ? "rotate-180" : ""}`}
                            >
                              <ChevronDownIcon width={13} height={13} />
                            </span>{" "}
                            Show diagnostic
                          </button>
                          {showDetails && (
                            <pre className="mono mt-2 whitespace-pre-wrap rounded-lg bg-red-100/60 p-3 text-[11px] leading-relaxed text-red-800">
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
                  className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 transition-colors hover:bg-slate-50"
                >
                  <ChevronLeftIcon width={15} height={15} /> Back
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDispense}
                  disabled={view === "s2-submitting"}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:bg-brand-600/70"
                >
                  {view === "s2-submitting" ? (
                    <>
                      <Spinner size={15} /> Submitting to ΗΔΥΚΑ…
                    </>
                  ) : view === "s2-failure" ? (
                    "Retry dispense"
                  ) : (
                    "Confirm dispense"
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ══════════════ SUCCESS ══════════════ */}
          {success && (
            <div className="px-6 py-10 text-center">
              <div className="mx-auto flex h-16 w-16 animate-pop items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                <CheckIcon width={36} height={36} strokeWidth={2.5} />
              </div>
              <h2 id={titleId} className="mt-5 text-[20px] font-bold text-slate-900">
                Dispensed successfully
              </h2>
              <p className="mt-1.5 text-[13px] text-slate-500">
                {packVerified
                  ? "The dispense was recorded in ΗΔΥΚΑ and the pack decommissioned."
                  : "The dispense was recorded in ΗΔΥΚΑ. Pack decommission was not performed."}
              </p>
              <div className="mx-auto mt-5 max-w-[360px] rounded-xl border border-slate-200 bg-slate-50 px-4 py-1.5 text-left">
                {executionNo && (
                  <>
                    <SummaryRow label="Execution No">
                      <span className="mono">{executionNo}</span>
                    </SummaryRow>
                    <div className="border-t border-slate-200/70" />
                  </>
                )}
                <SummaryRow label="Prescription">
                  <span className="mono">{barcode}</span>
                </SummaryRow>
              </div>
              <div className="mt-6 flex items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 transition-colors hover:bg-slate-50"
                >
                  <PrinterIcon width={15} height={15} /> Print receipt
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg bg-brand-600 px-5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700"
                >
                  Back to counter
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
