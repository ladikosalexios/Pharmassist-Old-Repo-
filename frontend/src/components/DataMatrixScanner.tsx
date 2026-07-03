import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader, type IScannerControls } from "@zxing/browser";
import { BarcodeFormat, DecodeHintType } from "@zxing/library";
import { useTranslation } from "react-i18next";
import { BarcodeIcon, AlertTriangleIcon } from "./Icons";
import {
  HmvsSecureInput,
  type HmvsBlockReason,
  type HmvsSecureInputHandle,
} from "./HmvsSecureInput";

/**
 * DataMatrix scanner for HMVS pack codes.
 *
 * Reads GS1 DataMatrix (ECC200) via @zxing/browser from the device camera,
 * and falls back to manual / handheld-scanner input through HmvsSecureInput
 * — the same H1-guarded field that catches Caps Lock and wrong-keyboard-layout
 * mistakes on the rest of the dispense flow.
 *
 * The component does NOT parse GS1 AIs — it hands the RAW payload back to the
 * caller (DispenseWizard), which delegates parsing to ``lib/gs1.parseGs1``.
 */
// EMVS data-entry mode — how this payload was captured. Mirrors
// lib/hmvs.HmvsDataEntryMode, declared inline because the HMVS gateway is
// import-restricted to the dispense flow (see eslint.config.js); the parent
// (DispenseWizard) bridges the two structurally-identical unions. "non-manual"
// is the scanned value the Greek IQE accepts.
export type ScanEntryMode = "non-manual" | "manual";

export interface DataMatrixScannerProps {
  onScan: (rawPayload: string, entryMode: ScanEntryMode) => void;
  disabled?: boolean;
  /** Forwarded to HmvsSecureInput so the parent receives the same block signal. */
  onBlockChange?: (reason: HmvsBlockReason) => void;
}

// Dev-only convenience: a well-formed GS1 DataMatrix payload that mock HMVS
// verifies as Active — so the dispense flow can be driven without a hardware
// scanner. Real scans carry the FNC1 (0x1D) separator after variable-length AIs;
// a keyboard can't type it, so a hand-keyed string is impossible. This injects a
// correct one: (01) GTIN, (17) expiry, (10) batch, ⟨FNC1⟩, (21) serial-last.
// The serial is letter-only + random so repeated clicks add distinct packs and
// never contain "404" (the mock's unknown-pack sentinel). Gated behind
// import.meta.env.DEV — tree-shaken out of production builds.
function devSamplePack(): string {
  const FNC1 = "\u001d"; // GS1 group separator (0x1D)
  const alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ";
  const bytes = new Uint8Array(10);
  globalThis.crypto?.getRandomValues?.(bytes);
  let serial = "DEV";
  for (const b of bytes) serial += alpha[b % alpha.length];
  // "01"+GTIN(14) "17"+expiry(6) "10"+batch ⟨FNC1⟩ "21"+serial(last, no terminator)
  return "]d2" + "01" + "05201234500031" + "17" + "271231" + "10" + "LOT42" + FNC1 + "21" + serial;
}

export function DataMatrixScanner({ onScan, disabled, onBlockChange }: DataMatrixScannerProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const secureInputRef = useRef<HmvsSecureInputHandle>(null);
  const onScanRef = useRef(onScan);
  useEffect(() => {
    onScanRef.current = onScan;
  });

  const [mode, setMode] = useState<"input" | "camera">("input");
  const [manualValue, setManualValue] = useState("");
  const [blockReason, setBlockReason] = useState<HmvsBlockReason>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // Propagate the H1 block reason up to the wizard so it can disable submit.
  useEffect(() => {
    onBlockChange?.(blockReason);
  }, [blockReason, onBlockChange]);

  const stopCamera = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
  }, []);

  useEffect(() => {
    if (mode !== "camera" || disabled) return;
    const hints = new Map<DecodeHintType, unknown>();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.DATA_MATRIX]);
    const reader = new BrowserMultiFormatReader(hints);

    let cancelled = false;
    setCameraError(null);

    reader
      .decodeFromVideoDevice(undefined, videoRef.current!, (result, _err, controls) => {
        if (cancelled) {
          controls.stop();
          return;
        }
        controlsRef.current = controls;
        if (result) {
          controls.stop();
          controlsRef.current = null;
          // Camera decode of the 2D DataMatrix → a genuine scan ("non-manual").
          onScanRef.current(result.getText(), "non-manual");
          setMode("input");
        }
      })
      .catch((e: unknown) => {
        // A `NotAllowedError` from getUserMedia means the browser denied (or
        // the user blocked) camera permission — that's a different failure
        // mode than missing hardware and deserves its own end-user copy.
        const denied = e instanceof Error && e.name === "NotAllowedError";
        setCameraError(
          denied ? t("dispense.cameraPermissionDenied") : t("dispense.cameraUnavailable"),
        );
        setMode("input");
      });

    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [mode, disabled, t, stopCamera]);

  function submitManual(e?: React.KeyboardEvent) {
    const v = manualValue.trim();
    if (!v) return;

    // Synchronous re-validation to prevent React batching races (e.g. Greek scan
    // followed immediately by Enter before state updates).
    if (!secureInputRef.current?.isClean(e)) return;

    // Detect fast wedge-scanner bursts vs slow human typing.
    const entryMode: ScanEntryMode = secureInputRef.current?.isBurst() ? "non-manual" : "manual";

    onScanRef.current(v, entryMode);
    setManualValue("");
  }

  return (
    <div>
      {mode === "input" ? (
        <>
          <HmvsSecureInput
            ref={secureInputRef}
            value={manualValue}
            onChange={setManualValue}
            onBlock={setBlockReason}
            ariaLabel={t("dispense.scanPrompt")}
            mono
            disabled={disabled}
            placeholder="]d20105700123456789..."
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                submitManual(e);
              }
            }}
          />
          <div className="mt-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setMode("camera")}
              disabled={disabled}
              className="flex items-center gap-1.5 text-[12.5px] font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 disabled:opacity-50"
            >
              <BarcodeIcon width={14} height={14} /> {t("dispense.useCamera")}
            </button>
            <button
              type="button"
              onClick={() => submitManual()}
              disabled={!manualValue.trim() || blockReason !== null || disabled}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-[12.5px] font-semibold text-white hover:bg-brand-700 disabled:bg-brand-600/60"
            >
              {t("dispense.addPack")}
            </button>
          </div>
          {import.meta.env.DEV && (
            <button
              type="button"
              onClick={() => onScanRef.current(devSamplePack(), "non-manual")}
              disabled={disabled}
              className="mt-2 w-full rounded-lg border border-dashed border-amber-300 dark:border-amber-500/40 bg-amber-50/50 dark:bg-amber-500/5 px-3 py-1.5 text-[12px] font-semibold text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10 disabled:opacity-50"
            >
              DEV · fill test pack
            </button>
          )}
          {cameraError && (
            <p className="mt-2 flex items-center gap-1.5 text-[12px] text-amber-700 dark:text-amber-400">
              <AlertTriangleIcon width={13} height={13} className="shrink-0" />
              {cameraError}
            </p>
          )}
        </>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-black">
          <video
            ref={videoRef}
            className="aspect-video w-full object-cover"
            muted
            playsInline
            aria-label={t("dispense.cameraPrompt")}
          />
          <div className="flex items-center justify-between bg-slate-50 dark:bg-slate-900 px-3 py-2">
            <span className="text-[12px] text-slate-500 dark:text-slate-400">
              {t("dispense.cameraPrompt")}
            </span>
            <button
              type="button"
              onClick={() => setMode("input")}
              className="text-[12px] font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100"
            >
              {t("dispense.cancelCamera")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
