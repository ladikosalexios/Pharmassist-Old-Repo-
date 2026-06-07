import { useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
      setLiveError(t("spc.errorNoAtc"));
      setLoading(false);
      return () => {
        active = false;
      };
    }
    getSpc(atcCode)
      .then((data) => {
        if (active) setSpc(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setLiveError(e instanceof ApiError ? e.message : t("spc.errorLoadLive"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [atcCode, t]);

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
          recommendedDosage: dosage || t("spc.notProvided"),
          contraindications,
          majorInteractions,
        };
      }
    }
    return null;
  }, [spc, fallback, t]);

  return (
    <section className="card overflow-hidden">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{t("spc.title")}</h2>
          <p className="text-xs text-slate-500">
            {drugName}
            {spc?.atcCode && (
              <>
                {" "}
                · <span className="font-mono">{spc.atcCode}</span>
              </>
            )}
            {spc?.version && <> · {spc.version}</>}
            {view?.source === "fallback" && <> · {t("spc.fromPrescriptionRecord")}</>}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setFullSpcOpen(true)}
          disabled={!spc}
          title={spc ? undefined : t("spc.fullSpcUnavailableTitle")}
          className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <FileTextIcon /> {t("spc.viewFullSpc")}
        </button>
      </header>

      <div className="p-6">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="spinner text-brand-600" /> {t("spc.loading")}
          </div>
        ) : !view ? (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
            <span>{liveError ?? t("spc.noData")}</span>
          </div>
        ) : (
          <>
            {view.source === "fallback" && (
              <div className="mb-5 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
                <span>
                  {t("spc.fallbackBanner")}
                  {liveError && <span className="ml-1 text-amber-700/80">({liveError})</span>}
                </span>
              </div>
            )}

            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t("spc.recommendedDosage")}
              </div>
              <p className="mt-2 rounded-lg bg-brand-50 p-4 text-sm leading-relaxed text-slate-700">
                {view.recommendedDosage}
              </p>
            </div>

            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t("spc.keyContraindications")}
              </div>
              {view.contraindications.length ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {view.contraindications.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-500">{t("spc.noneRecorded")}</p>
              )}
            </div>

            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t("spc.majorInteractions")}
              </div>
              {view.majorInteractions.length ? (
                <div className="mt-2 space-y-2">
                  {view.majorInteractions.map((it, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"
                    >
                      <span className="font-bold text-slate-900">{it.drug}</span>
                      <span className="ml-2 text-amber-800">— {it.effect}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-500">{t("spc.noneRecorded")}</p>
              )}
            </div>
          </>
        )}
      </div>

      {spc && <FullSpcModal open={fullSpcOpen} spc={spc} onClose={() => setFullSpcOpen(false)} />}
    </section>
  );
}

function FullSpcModal({
  open,
  spc,
  onClose,
}: {
  open: boolean;
  spc: SpcDetails;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  useModalRegistration(open);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 animate-fade-in"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
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
              {spc.drugName} — {t("spc.fullSpc")}
            </h2>
            <p className="text-xs text-slate-500">
              <span className="font-mono">{spc.atcCode}</span> · {spc.version} · {t("spc.updated")}{" "}
              {formatDate(spc.updatedAt)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            aria-label={t("spc.closeFullSpc")}
          >
            <XIcon />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">
            {spc.fullSpcText ?? t("spc.fullSpcTextUnavailable")}
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
              {t("spc.openOnEof")} ↗
            </a>
          ) : (
            <span />
          )}
          <button type="button" onClick={onClose} className="btn btn-outline">
            {t("spc.close")}
          </button>
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
