import { useEffect, useId, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircleIcon, FileTextIcon, XIcon } from "./Icons";
import { ApiError, getSpc } from "../lib/api";
import { useModalRegistration } from "../lib/keyboard";
import type { Interaction, SpcDetails } from "../types";

export interface SpcFallback {
  recommendedDosage?: string | null;
  contraindications?: string[] | null;
  majorInteractions?: Interaction[] | null;
}

interface SPCQuickReferenceProps {
  drugName: string;
  atcCode: string;
  /**
   * Cached/static SPC info from the prescription payload. Used as a fallback
   * when the live /spc/:atcCode call fails so the card always shows something
   * useful instead of just an error banner.
   */
  fallback?: SpcFallback;
}

interface View {
  source: "live" | "fallback";
  recommendedDosage: string;
  contraindications: string[];
  majorInteractions: Interaction[];
  /** Only present when source === "live" */
  spc?: SpcDetails;
}

export function SPCQuickReference({ drugName, atcCode, fallback }: SPCQuickReferenceProps) {
  const [spc, setSpc] = useState<SpcDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [fullSpcOpen, setFullSpcOpen] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLiveError(null);
    setSpc(null);
    if (!atcCode) {
      setLiveError("This medication has no ATC code on file, so the live SPC cannot be loaded.");
      setLoading(false);
      return () => { active = false; };
    }
    getSpc(atcCode)
      .then((data) => { if (active) setSpc(data); })
      .catch((e: unknown) => {
        if (!active) return;
        setLiveError(e instanceof ApiError ? e.message : "Could not load the live SPC.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [atcCode]);

  const view: View | null = useMemo(() => {
    if (spc) {
      return {
        source: "live",
        recommendedDosage: spc.recommendedDosage,
        contraindications: spc.contraindications,
        majorInteractions: spc.majorInteractions,
        spc,
      };
    }
    if (fallback) {
      const dosage = fallback.recommendedDosage ?? "";
      const contraindications = fallback.contraindications ?? [];
      const majorInteractions = fallback.majorInteractions ?? [];
      if (dosage || contraindications.length || majorInteractions.length) {
        return {
          source: "fallback",
          recommendedDosage: dosage || "Not provided in the prescription record.",
          contraindications,
          majorInteractions,
        };
      }
    }
    return null;
  }, [spc, fallback]);

  return (
    <section className="card overflow-hidden">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">SPC Quick Reference</h2>
          <p className="text-xs text-slate-500">
            {drugName}
            {spc?.atcCode && <> · <span className="font-mono">{spc.atcCode}</span></>}
            {spc?.version && <> · {spc.version}</>}
            {view?.source === "fallback" && <> · from prescription record</>}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setFullSpcOpen(true)}
          disabled={!spc}
          title={spc ? undefined : "Live SPC document is not available."}
          className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <FileTextIcon /> View Full SPC
        </button>
      </header>

      <div className="p-6">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="spinner text-brand-600" /> Loading SPC…
          </div>
        ) : !view ? (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
            <span>{liveError ?? "No SPC data available for this medication."}</span>
          </div>
        ) : (
          <>
            {view.source === "fallback" && (
              <div className="mb-5 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
                <span>
                  Live SPC service unavailable — showing data captured with the prescription.
                  {liveError && <span className="ml-1 text-amber-700/80">({liveError})</span>}
                </span>
              </div>
            )}

            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">SPC Recommended Dosage</div>
              <p className="mt-2 rounded-lg bg-brand-50 p-4 text-sm leading-relaxed text-slate-700">
                {view.recommendedDosage}
              </p>
            </div>

            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Key Contraindications</div>
              {view.contraindications.length ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {view.contraindications.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-500">None recorded.</p>
              )}
            </div>

            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Major Interactions</div>
              {view.majorInteractions.length ? (
                <div className="mt-2 space-y-2">
                  {view.majorInteractions.map((it, i) => (
                    <div key={i} className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                      <span className="font-bold text-slate-900">{it.drug}</span>
                      <span className="ml-2 text-amber-800">— {it.effect}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-500">None recorded.</p>
              )}
            </div>
          </>
        )}
      </div>

      {spc && (
        <FullSpcModal
          open={fullSpcOpen}
          spc={spc}
          onClose={() => setFullSpcOpen(false)}
        />
      )}
    </section>
  );
}

function FullSpcModal({
  open, spc, onClose,
}: {
  open: boolean;
  spc: SpcDetails;
  onClose: () => void;
}) {
  useModalRegistration(open);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 animate-fade-in"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-cardLg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-6 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-slate-900">
              {spc.drugName} — Full SPC
            </h2>
            <p className="text-xs text-slate-500">
              <span className="font-mono">{spc.atcCode}</span> · {spc.version} · Updated {formatDate(spc.updatedAt)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            aria-label="Close full SPC"
          >
            <XIcon />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">
            {spc.fullSpcText ?? "Full SPC text is not available in this build."}
          </pre>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-6 py-3">
          {spc.fullSpcUrl ? (
            <a
              href={spc.fullSpcUrl}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-brand-600 hover:underline"
            >
              Open on EOF.gr ↗
            </a>
          ) : <span />}
          <button type="button" onClick={onClose} className="btn btn-outline">Close</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
