import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CheckCircleIcon,
  AlertTriangleIcon,
  AlertOctagonIcon,
  AlertCircleIcon,
  ChevronDownIcon,
} from "./Icons";
import { ApiError, getSafetyChecks } from "../lib/api";
import type { CheckStatus, SafetyCheck } from "../types";

interface SevStyle {
  ring: string;
  iconClass: string;
  icon: React.ReactNode;
  tag: string;
  /** i18n key (within the "safetyChecks" namespace) for the severity tag label. */
  tagLabelKey: string;
  titleClass: string;
  detailClass: string;
  /** Border for the recommended-action inner box (kept neutral of the tint). */
  actionBox: string;
  pulse: boolean;
}

const SEV: Record<CheckStatus, SevStyle> = {
  block: {
    ring: "border-red-300 bg-red-50 dark:border-red-500/30 dark:bg-red-500/10",
    iconClass: "text-red-600 dark:text-red-400",
    icon: <AlertOctagonIcon width={16} height={16} />,
    tag: "bg-red-600 text-white",
    tagLabelKey: "safetyChecks.tagCritical",
    titleClass: "text-red-800 dark:text-red-400",
    detailClass: "text-slate-700 dark:text-slate-300",
    actionBox: "border-red-200 dark:border-red-500/30",
    pulse: true,
  },
  review: {
    ring: "border-amber-300 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10",
    iconClass: "text-amber-600 dark:text-amber-400",
    icon: <AlertTriangleIcon width={16} height={16} />,
    tag: "bg-amber-500 text-white",
    tagLabelKey: "safetyChecks.tagReview",
    titleClass: "text-amber-800 dark:text-amber-400",
    detailClass: "text-slate-700 dark:text-slate-300",
    actionBox: "border-amber-200 dark:border-amber-500/30",
    pulse: false,
  },
  ok: {
    ring: "border-emerald-200 bg-emerald-50/60 dark:border-emerald-500/30 dark:bg-emerald-500/10",
    iconClass: "text-emerald-600 dark:text-emerald-400",
    icon: <CheckCircleIcon width={16} height={16} />,
    tag: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
    tagLabelKey: "safetyChecks.tagOk",
    titleClass: "text-slate-700 dark:text-slate-300",
    detailClass: "text-slate-500 dark:text-slate-400",
    actionBox: "border-emerald-200 dark:border-emerald-500/30",
    pulse: false,
  },
};

function Skl({ w = "100%", h = 14, mt = 0 }: { w?: string; h?: number; mt?: number }) {
  return (
    <div className="sk animate-shimmer rounded" style={{ width: w, height: h, marginTop: mt }} />
  );
}

interface SafetyChecksPanelProps {
  rxId: string;
  /** Bump to force a re-fetch (e.g. after a patient factor is toggled). */
  refreshKey?: number;
  onBlockChange?: (hasBlock: boolean) => void;
  onLoadingChange?: (loading: boolean) => void;
}

export function SafetyChecksPanel({
  rxId,
  refreshKey,
  onBlockChange,
  onLoadingChange,
}: SafetyChecksPanelProps) {
  const { t } = useTranslation();
  const [checks, setChecks] = useState<SafetyCheck[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    onLoadingChange?.(true);
    setError(null);
    getSafetyChecks(rxId)
      .then((data) => {
        if (!active) return;
        setChecks(data);
        onBlockChange?.(data.some((c) => c.status === "block"));
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : t("safetyChecks.loadError"));
        onBlockChange?.(false);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        onLoadingChange?.(false);
      });
    return () => {
      active = false;
    };
  }, [rxId, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
      {/* header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[12px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
          {t("safetyChecks.title")}
        </h2>
        {!error && (
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            {t("safetyChecks.live")}
          </span>
        )}
      </div>

      {/* legend */}
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400 dark:text-slate-500">
        <span className="flex items-center gap-1">
          <CheckCircleIcon
            width={12}
            height={12}
            className="text-emerald-500 dark:text-emerald-400"
          />{" "}
          {t("safetyChecks.legendOk")}
        </span>
        <span className="flex items-center gap-1">
          <AlertTriangleIcon
            width={12}
            height={12}
            className="text-amber-500 dark:text-amber-400"
          />{" "}
          {t("safetyChecks.legendReview")}
        </span>
        <span className="flex items-center gap-1">
          <AlertOctagonIcon width={12} height={12} className="text-red-500 dark:text-red-400" />{" "}
          {t("safetyChecks.legendImmediateAction")}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
              <Skl w="60%" h={13} />
              <Skl w="90%" h={11} mt={8} />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12.5px] text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : (
        <div className="space-y-2.5">
          {checks?.map((c) => (
            <CheckRow key={c.id} check={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function CheckRow({ check }: { check: SafetyCheck }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(check.status === "block");
  const s = SEV[check.status];
  const expandable = check.status !== "ok";

  return (
    <div className={`rounded-lg border p-3 ${s.ring} ${s.pulse ? "animate-pulse-red-border" : ""}`}>
      <div className="flex items-start gap-2.5">
        <span className={`mt-0.5 shrink-0 ${s.iconClass}`}>{s.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`text-[13px] font-bold ${s.titleClass}`}>{check.name}</span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${s.tag}`}>
              {t(s.tagLabelKey)}
            </span>
          </div>
          {expandable && (
            <p className={`mt-1 text-[12.5px] leading-snug ${s.detailClass}`}>{check.message}</p>
          )}
          {(check.details || check.recommendedAction) && (
            <div id={`check-details-${check.id}`} hidden={!open}>
              {check.details && (
                <p className="mono mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                  {check.details}
                </p>
              )}
              {check.recommendedAction && (
                <p
                  className={`mt-1.5 rounded border ${s.actionBox} bg-white px-2.5 py-1.5 text-[11.5px] leading-snug text-slate-700 dark:bg-slate-800 dark:text-slate-300`}
                >
                  {check.recommendedAction}
                </p>
              )}
            </div>
          )}
          {expandable && (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={`check-details-${check.id}`}
              onClick={() => setOpen((o) => !o)}
              className={`mt-1.5 flex items-center gap-0.5 text-[11.5px] font-semibold ${s.iconClass}`}
            >
              {t("safetyChecks.details")}{" "}
              <span className={`transition-transform ${open ? "rotate-180" : ""}`}>
                <ChevronDownIcon width={13} height={13} />
              </span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
