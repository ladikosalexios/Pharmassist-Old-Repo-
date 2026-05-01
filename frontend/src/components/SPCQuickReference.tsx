import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircleIcon, FileTextIcon, XIcon } from "./Icons";
import { ApiError, getSpc } from "../lib/api";
import type { SpcDetails } from "../types";

interface SPCQuickReferenceProps {
  drugName: string;
  atcCode: string;
}

export function SPCQuickReference({ drugName, atcCode }: SPCQuickReferenceProps) {
  const [spc, setSpc] = useState<SpcDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fullSpcOpen, setFullSpcOpen] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setSpc(null);
    if (!atcCode) {
      setError("This medication has no ATC code on file, so the SPC cannot be loaded.");
      setLoading(false);
      return () => { active = false; };
    }
    getSpc(atcCode)
      .then((data) => { if (active) setSpc(data); })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load the SPC.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [atcCode]);

  return (
    <section className="card overflow-hidden">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">SPC Quick Reference</h2>
          <p className="text-xs text-slate-500">
            {drugName}
            {spc?.atcCode && <> · <span className="font-mono">{spc.atcCode}</span></>}
            {spc?.version && <> · {spc.version}</>}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setFullSpcOpen(true)}
          disabled={loading || !!error || !spc}
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
        ) : error ? (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : spc ? (
          <>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">SPC Recommended Dosage</div>
              <p className="mt-2 rounded-lg bg-brand-50 p-4 text-sm leading-relaxed text-slate-700">
                {spc.recommendedDosage}
              </p>
            </div>

            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Key Contraindications</div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {spc.contraindications.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>

            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Major Interactions</div>
              <div className="mt-2 space-y-2">
                {spc.majorInteractions.map((it, i) => (
                  <div key={i} className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                    <span className="font-bold text-slate-900">{it.drug}</span>
                    <span className="ml-2 text-amber-800">— {it.effect}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}
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
