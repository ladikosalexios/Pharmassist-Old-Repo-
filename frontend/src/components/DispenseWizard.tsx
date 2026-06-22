import { useCallback, useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import {
  XIcon,
  CheckCircleIcon,
  AlertOctagonIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
  ChevronDownIcon,
  CheckIcon,
  PrinterIcon,
  AlertCircleIcon,
  TrashIcon,
  RefreshIcon,
} from "./Icons";
import { useTranslation } from "react-i18next";
import { ApiError, approvePrescription } from "../lib/api";
import {
  hmvsDecommission,
  hmvsReactivate,
  hmvsVerify,
  type HmvsDataEntryMode,
  type HmvsPackKey,
  type HmvsPackResponse,
} from "../lib/hmvs";
import { useModalRegistration } from "../lib/keyboard";
import { DataMatrixScanner } from "./DataMatrixScanner";
import { type HmvsBlockReason } from "./HmvsSecureInput";
import { parseGs1, isCompletePack } from "../lib/gs1";

// ── Per-pack state machine ──────────────────────────────────────────────────
//
// pending     — the pharmacist added a payload, parsing/verification not started
// verifying   — HMVS verify call in flight (or scheduled to run)
// verified    — HMVS returned 200 + state=Active (or bulk-inferred from a
//               same-batch local sibling — see ``verifyPack``)
// blocked     — HMVS returned a non-Active response (recalled, withdrawn,
//               expired, suspended, already supplied). ``warning`` carries
//               the upstream copy so the pharmacist sees WHY.
// supplying   — PATCH Supplied in flight.
// supplied    — PATCH Supplied returned ok.
// supply-failed — PATCH Supplied failed (or returned ok=false).
//
// Malformed payloads do NOT enter this list — onPackScanned surfaces them via
// `scanError` and never adds the entry, so the pharmacist re-scans before the
// pack reaches the registry.
type PackStatus =
  | "pending"
  | "verifying"
  | "verified"
  | "blocked"
  | "supplying"
  | "supplied"
  | "supply-failed";

interface PackEntry {
  id: string;
  rawPayload: string;
  /** Parsed GS1 (gtin/serial/batch/expiry). Only populated when complete. */
  key?: HmvsPackKey;
  /** How this pack was captured (camera 2D scan vs hand-keyed) — sent to EMVS
   * on verify + supply so a scan is recorded as a scan, not "manual". */
  entryMode?: HmvsDataEntryMode;
  status: PackStatus;
  /**
   * "bulk" when verification was skipped because a previously-verified pack
   * of the same GTIN+batch returned isIntermarket=false (local homogeneous
   * set, single-verify covers the rest). "single" for verified-on-the-wire.
   */
  verifyMethod?: "single" | "bulk";
  /** Response from the registry (or inherited for bulk). */
  verify?: HmvsPackResponse;
  supply?: HmvsPackResponse;
  /** Free-text error to surface in the row. */
  error?: string;
}

type WizardView = "verify" | "confirm" | "submitting" | "success" | "rollback" | "failure";

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

function newPackId(): string {
  // crypto.randomUUID is available in all modern browsers — good enough
  // for an in-memory list key.
  return (
    globalThis.crypto?.randomUUID?.() ?? `pack-${Math.floor(performance.now() * 1000).toString(36)}`
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

  const [view, setView] = useState<WizardView>("verify");
  const [packs, setPacks] = useState<PackEntry[]>([]);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scannerBlocked, setScannerBlocked] = useState<HmvsBlockReason>(null);
  const [counsel, setCounsel] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [dispenseError, setDispenseError] = useState<string | null>(null);
  const [dispenseErrorDetail, setDispenseErrorDetail] = useState<string | null>(null);
  const [executionNo, setExecutionNo] = useState<string | null>(null);

  // Reset state when the wizard opens.
  useEffect(() => {
    if (!open) return;
    setView("verify");
    setPacks([]);
    setScanError(null);
    setScannerBlocked(null);
    setCounsel(false);
    setShowDetails(false);
    setDispenseError(null);
    setDispenseErrorDetail(null);
    setExecutionNo(null);
  }, [open]);

  // Esc closes the modal unless something irreversible is in flight.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      const blocking = view === "submitting" || view === "rollback";
      if (e.key === "Escape" && !blocking) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, view, onClose]);

  function setPack(id: string, patch: Partial<PackEntry>) {
    setPacks((cur) => cur.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  }

  const verifyPack = useCallback(
    async (entry: PackEntry, siblings: PackEntry[]) => {
      // ── Bulk verification by inference ────────────────────────────────────
      // The HMVS Bulk Verification feature allows a single verify call to
      // cover a homogeneous local (non-intermarket) set: one pack on the wire,
      // the rest treated as verified by inheritance. Intermarket packs and
      // heterogeneous sets always verify single-per-pack.
      const sibling = siblings.find(
        (p) =>
          p.id !== entry.id &&
          p.status === "verified" &&
          p.verifyMethod === "single" &&
          p.verify?.isIntermarket === false &&
          p.key?.gtin === entry.key?.gtin &&
          p.key?.batch === entry.key?.batch,
      );
      if (sibling && sibling.verify) {
        setPack(entry.id, {
          status: "verified",
          verifyMethod: "bulk",
          verify: { ...sibling.verify, serial: entry.key?.serial ?? sibling.verify.serial },
        });
        return;
      }

      try {
        const result = await hmvsVerify(entry.key!, entry.entryMode);
        // The dispense flow accepts ONLY packs reported Active by the
        // registry. Anything else (Supplied, Recalled, Withdrawn, …) lands
        // the pack in 'blocked' so the pharmacist sees the registry warning.
        if (result.ok && result.state === "Active") {
          setPack(entry.id, { status: "verified", verifyMethod: "single", verify: result });
        } else {
          setPack(entry.id, {
            status: "blocked",
            verify: result,
            error: result.warning ?? result.information ?? t("dispense.verifyFailedTitle"),
          });
        }
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : t("dispense.verifyGenericError");
        setPack(entry.id, { status: "blocked", error: msg });
      }
    },
    [t],
  );

  function onPackScanned(rawPayload: string, entryMode: HmvsDataEntryMode) {
    setScanError(null);
    const fields = parseGs1(rawPayload);
    if (!isCompletePack(fields)) {
      setScanError(t("dispense.scanMalformed"));
      return;
    }
    // Reject duplicates by serial — a pack is dispensed once.
    const dupKey = `${fields.gtin}:${fields.serial}`;
    setPacks((cur) => {
      if (cur.some((p) => p.key && `${p.key.gtin}:${p.key.serial}` === dupKey)) {
        setScanError(t("dispense.duplicatePack"));
        return cur;
      }
      const entry: PackEntry = {
        id: newPackId(),
        rawPayload,
        key: fields,
        entryMode,
        status: "verifying",
      };
      // Kick off verify against the soon-to-be-updated list. Known limitation:
      // bulk-by-inference (verifyPack) requires the sibling pack's status to be
      // "verified" already, so two packs scanned in quick succession both hit
      // the registry on the wire — the second's siblings snapshot only sees the
      // first as "verifying". This is intentional: serialising on a sibling we
      // haven't actually verified would let a single bad-state response taint
      // the whole batch. Sequential-scan is the documented usage.
      queueMicrotask(() => verifyPack(entry, [...cur, entry]));
      return [...cur, entry];
    });
  }

  function removePack(id: string) {
    setPacks((cur) => cur.filter((p) => p.id !== id));
  }

  async function retryVerify(id: string) {
    const entry = packs.find((p) => p.id === id);
    if (!entry || !entry.key) return;
    setPack(id, { status: "verifying", verify: undefined, error: undefined });
    await verifyPack({ ...entry, status: "verifying" }, packs);
  }

  const allVerified = packs.length > 0 && packs.every((p) => p.status === "verified");

  async function handleConfirmDispense() {
    setView("submitting");
    setDispenseError(null);
    setDispenseErrorDetail(null);

    // ── Phase 1: PATCH Supplied for every pack, sequentially ──────────────
    // Sequential keeps the audit trail clean and lets us stop at the first
    // failure (so a partial supply chain is small and easy to reactivate).
    const ordered = packs.slice();
    for (const p of ordered) {
      if (!p.key) continue;
      setPack(p.id, { status: "supplying" });
      try {
        const result = await hmvsDecommission(p.key, p.entryMode);
        if (result.ok || result.queued) {
          setPack(p.id, { status: "supplied", supply: result });
        } else {
          setPack(p.id, {
            status: "supply-failed",
            supply: result,
            error: result.warning ?? result.information ?? t("dispense.supplyFailed"),
          });
          setDispenseError(t("dispense.supplyHaltedTitle"));
          setDispenseErrorDetail(
            `pack: ${p.key.gtin}/${p.key.serial}\noperationCode: ${result.operationCode ?? "—"}\n${result.warning ?? ""}`,
          );
          setView("failure");
          return;
        }
      } catch (e) {
        const detail =
          e instanceof ApiError
            ? `${e.status} ${e.message}`
            : e instanceof Error
              ? e.message
              : String(e);
        setPack(p.id, { status: "supply-failed", error: detail });
        setDispenseError(t("dispense.supplyHaltedTitle"));
        setDispenseErrorDetail(`pack: ${p.key.gtin}/${p.key.serial}\n${detail}`);
        setView("failure");
        return;
      }
    }

    // ── Phase 2: record the dispense in ΗΔΥΚΑ ─────────────────────────────
    // Every pack in `ordered` is now Supplied (we returned early on any
    // failure). Pass their GS1 keys so the eDispensation supply lines carry the
    // real ΕΟΦ/QR serial instead of the synthetic placeholder.
    const dispensePacks = ordered
      .filter((p) => p.key)
      .map((p) => ({
        gtin: p.key!.gtin,
        serial: p.key!.serial,
        batch: p.key!.batch,
        expiry: p.key!.expiry,
      }));
    try {
      const result = await approvePrescription(rxId, dispensePacks);
      setExecutionNo(result.executionNo ?? null);
      setView("success");
      onDispensed(result.status);
    } catch (e) {
      if (e instanceof ApiError) {
        setDispenseError(t("dispense.dispenseRejected", { message: e.message }));
        setDispenseErrorDetail(`rxId: ${rxId}\nstatus: ${e.status}\n${e.message}`);
      } else {
        setDispenseError(t("dispense.dispenseGenericError"));
      }
      setView("failure");
    }
  }

  async function handleReactivateSupplied() {
    setView("rollback");
    // Walk every pack we've already moved to Supplied and PATCH back to Active.
    // Each reactivate is idempotency-guarded by the backend so a partial first
    // rollback can be safely retried.
    let anyFailed = false;
    for (const p of packs) {
      if (p.status !== "supplied" || !p.key) continue;
      try {
        const result = await hmvsReactivate(p.key, p.entryMode);
        if (result.ok || result.queued) {
          setPack(p.id, { status: "verified", supply: undefined, error: undefined });
        } else {
          anyFailed = true;
          setPack(p.id, {
            error: result.warning ?? result.information ?? t("dispense.reactivateFailed"),
          });
        }
      } catch (e) {
        anyFailed = true;
        const msg = e instanceof ApiError ? e.message : t("dispense.reactivateFailed");
        setPack(p.id, { error: msg });
      }
    }
    if (anyFailed) {
      // A reactivate failed → leave the failure banner up so the pharmacist
      // sees that some packs are stuck Supplied and can retry.
      setView("failure");
    } else {
      // Clean rollback — drop the prior failure banner and send the wizard back
      // to step 1 so the pharmacist can re-scan / re-confirm cleanly.
      setDispenseError(null);
      setDispenseErrorDetail(null);
      setView("verify");
    }
  }

  if (!open) return null;

  const step: 1 | 2 =
    view === "confirm" ||
    view === "submitting" ||
    view === "success" ||
    view === "failure" ||
    view === "rollback"
      ? 2
      : 1;
  const success = view === "success";
  const blockingView = view === "submitting" || view === "rollback";

  return createPortal(
    <div
      className="fixed inset-0 z-50 animate-fade-in bg-slate-900/40"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !blockingView) onClose();
      }}
    >
      <div className="flex h-full items-center justify-center p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="w-full max-w-[600px] animate-modal-in overflow-hidden rounded-2xl bg-white dark:bg-slate-900 shadow-modal"
        >
          {!success && (
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4">
              <StepDots step={step} />
              <button
                type="button"
                onClick={onClose}
                disabled={blockingView}
                aria-label={t("dispense.cancel")}
                className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300 disabled:opacity-40"
              >
                <XIcon width={18} height={18} />
              </button>
            </div>
          )}

          {/* ══════════════ STEP 1 — verify packs ══════════════ */}
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

              <div className="mt-5">
                <DataMatrixScanner onScan={onPackScanned} onBlockChange={setScannerBlocked} />
                {scanError && (
                  <p className="mt-2 flex items-center gap-1.5 text-[12.5px] font-medium text-red-700 dark:text-red-400">
                    <AlertCircleIcon width={13} height={13} className="shrink-0" /> {scanError}
                  </p>
                )}
                {scannerBlocked !== null && (
                  <p className="mt-1 text-[11.5px] text-slate-500 dark:text-slate-400">
                    {t("dispense.fixSecureInputFirst")}
                  </p>
                )}
              </div>

              {/* Pack list */}
              {packs.length > 0 && (
                <ul
                  className="mt-5 space-y-2"
                  aria-live="polite"
                  aria-label={t("dispense.packListLabel")}
                >
                  {packs.map((p) => (
                    <PackRow key={p.id} pack={p} onRemove={removePack} onRetry={retryVerify} />
                  ))}
                </ul>
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
                <button
                  type="button"
                  onClick={() => setView("confirm")}
                  disabled={!allVerified}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:bg-brand-600/60"
                >
                  {t("dispense.proceedToConfirm")} <ChevronRightIcon width={15} height={15} />
                </button>
              </div>
            </div>
          )}

          {/* ══════════════ STEP 2 — confirm / submitting / failure ══════════════ */}
          {step === 2 && !success && (
            <div className="px-6 py-6">
              <h2 id={titleId} className="text-[18px] font-bold text-slate-900 dark:text-slate-100">
                {t("dispense.step2Title")}
              </h2>

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
                <div className="border-t border-slate-200/70 dark:border-slate-800" />
                <SummaryRow label={t("dispense.packsToSupply")} strong>
                  {packs.length}
                </SummaryRow>
              </div>

              <ul className="mt-4 space-y-2">
                {packs.map((p) => (
                  <PackRow key={p.id} pack={p} compact />
                ))}
              </ul>

              <p className="mt-3 text-[12px] text-slate-500 dark:text-slate-400">
                {t("dispense.decommissionNote")}
              </p>

              {/* TODO(FR-3): pass `counsel` to approvePrescription once the
                  /prescriptions/{id}/approve body accepts a counseling flag.
                  For now the checkbox records intent only — the post-dispense
                  Instructions flow remains the canonical counselling surface. */}
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

              {view === "failure" && dispenseError && (
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
                      {packs.some((p) => p.status === "supplied") && (
                        <button
                          type="button"
                          onClick={handleReactivateSupplied}
                          disabled={view !== "failure"}
                          className="mt-3 flex items-center gap-1.5 rounded-lg border border-red-300 dark:border-red-500/40 bg-white dark:bg-slate-900 px-3 py-1.5 text-[12.5px] font-semibold text-red-700 dark:text-red-400 transition-colors hover:bg-red-50 dark:hover:bg-red-500/10"
                        >
                          <RefreshIcon width={13} height={13} /> {t("dispense.reactivateSupplied")}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="mt-6 flex items-center justify-between gap-2.5">
                <button
                  type="button"
                  onClick={() => {
                    setView("verify");
                    setShowDetails(false);
                  }}
                  disabled={blockingView}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60 disabled:opacity-50"
                >
                  <ChevronLeftIcon width={15} height={15} /> {t("dispense.back")}
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDispense}
                  disabled={blockingView || !allVerified}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:bg-brand-600/70"
                >
                  {view === "submitting" ? (
                    <>
                      <Spinner size={15} /> {t("dispense.submittingToHdyka")}
                    </>
                  ) : view === "rollback" ? (
                    <>
                      <Spinner size={15} /> {t("dispense.reactivating")}
                    </>
                  ) : view === "failure" ? (
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
                {t("dispense.successBodyVerified", { count: packs.length })}
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
                <div className="border-t border-slate-200/70 dark:border-slate-800" />
                <SummaryRow label={t("dispense.packsDispensed")}>{packs.length}</SummaryRow>
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

// ── Pack row ────────────────────────────────────────────────────────────────

function PackRow({
  pack,
  onRemove,
  onRetry,
  compact,
}: {
  pack: PackEntry;
  onRemove?: (id: string) => void;
  onRetry?: (id: string) => void;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const serial = pack.key?.serial ?? "—";
  const productName = pack.verify?.productName ?? null;
  const nhrn = pack.verify?.nhrn ?? null;
  // Surface the registry alert id (raised on e.g. stolen/recalled/unknown packs)
  // alongside the warning, so the HMVO testbook alert screenshots show it.
  const alertId = pack.verify?.alertId ?? pack.supply?.alertId ?? null;
  return (
    <li className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 px-3.5 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="mono text-[12.5px] text-slate-700 dark:text-slate-200">
              ⋯{serial.slice(-8)}
            </span>
            <PackStatusBadge pack={pack} />
          </div>
          <p className="mt-0.5 text-[11.5px] text-slate-500 dark:text-slate-400">
            {t("dispense.serialLabel")}: <span className="mono break-all">{serial}</span>
          </p>
          {productName && (
            <p className="mt-0.5 truncate text-[12px] text-slate-500 dark:text-slate-400">
              {productName}
            </p>
          )}
          {nhrn && (
            <p className="mt-0.5 text-[11.5px] text-slate-500 dark:text-slate-400">
              {t("dispense.nhrnLabel")}: <span className="mono">{nhrn}</span>
            </p>
          )}
          {pack.error && pack.status !== "verified" && pack.status !== "supplied" && (
            <p className="mt-1 text-[12px] text-red-700 dark:text-red-400">{pack.error}</p>
          )}
          {alertId && (
            <p className="mt-0.5 text-[11.5px] text-red-700 dark:text-red-400">
              {t("dispense.alertIdLabel")}: <span className="mono break-all">{alertId}</span>
            </p>
          )}
        </div>
        {!compact && (
          <div className="flex items-center gap-1">
            {pack.status === "blocked" && onRetry && (
              <button
                type="button"
                onClick={() => onRetry(pack.id)}
                className="rounded p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200"
                aria-label={t("dispense.retryVerify")}
                title={t("dispense.retryVerify")}
              >
                <RefreshIcon width={14} height={14} />
              </button>
            )}
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(pack.id)}
                className="rounded p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-red-600 dark:hover:text-red-400"
                aria-label={t("dispense.removePack")}
                title={t("dispense.removePack")}
              >
                <TrashIcon width={14} height={14} />
              </button>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function PackStatusBadge({ pack }: { pack: PackEntry }) {
  const { t } = useTranslation();
  switch (pack.status) {
    case "verifying":
      return (
        <Badge tone="brand">
          <Spinner size={10} /> {t("dispense.statusVerifying")}
        </Badge>
      );
    case "verified":
      return (
        <Badge tone="emerald">
          <CheckCircleIcon width={11} height={11} />{" "}
          {pack.verifyMethod === "bulk"
            ? t("dispense.statusVerifiedBulk")
            : t("dispense.statusVerified")}
        </Badge>
      );
    case "blocked":
      return (
        <Badge tone="red">
          <AlertOctagonIcon width={11} height={11} /> {t("dispense.statusBlocked")}
        </Badge>
      );
    case "supplying":
      return (
        <Badge tone="brand">
          <Spinner size={10} /> {t("dispense.statusSupplying")}
        </Badge>
      );
    case "supplied":
      return (
        <Badge tone="emerald">
          <CheckCircleIcon width={11} height={11} /> {t("dispense.statusSupplied")}
        </Badge>
      );
    case "supply-failed":
      return (
        <Badge tone="red">
          <AlertOctagonIcon width={11} height={11} /> {t("dispense.statusSupplyFailed")}
        </Badge>
      );
    case "pending":
    default:
      return <Badge tone="slate">{t("dispense.statusPending")}</Badge>;
  }
}

function Badge({
  tone,
  children,
}: {
  tone: "brand" | "emerald" | "red" | "amber" | "slate";
  children: React.ReactNode;
}) {
  const cls = {
    brand:
      "bg-brand-50 text-brand-700 border-brand-200 dark:bg-brand-500/10 dark:text-brand-400 dark:border-brand-500/30",
    emerald:
      "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30",
    red: "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/30",
    amber:
      "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/30",
    slate:
      "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {children}
    </span>
  );
}
