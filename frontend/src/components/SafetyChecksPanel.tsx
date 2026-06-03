import { useEffect, useState } from "react";
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
  tagLabel: string;
  titleClass: string;
  detailClass: string;
  pulse: boolean;
}

const SEV: Record<CheckStatus, SevStyle> = {
  block: {
    ring: "border-red-300 bg-red-50",
    iconClass: "text-red-600",
    icon: <AlertOctagonIcon width={16} height={16} />,
    tag: "bg-red-600 text-white",
    tagLabel: "CRITICAL",
    titleClass: "text-red-800",
    detailClass: "text-slate-700",
    pulse: true,
  },
  review: {
    ring: "border-amber-300 bg-amber-50",
    iconClass: "text-amber-600",
    icon: <AlertTriangleIcon width={16} height={16} />,
    tag: "bg-amber-500 text-white",
    tagLabel: "REVIEW",
    titleClass: "text-amber-800",
    detailClass: "text-slate-700",
    pulse: false,
  },
  ok: {
    ring: "border-emerald-200 bg-emerald-50/60",
    iconClass: "text-emerald-600",
    icon: <CheckCircleIcon width={16} height={16} />,
    tag: "bg-emerald-100 text-emerald-700",
    tagLabel: "OK",
    titleClass: "text-slate-700",
    detailClass: "text-slate-500",
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
  onBlockChange?: (hasBlock: boolean) => void;
}

export function SafetyChecksPanel({ rxId, onBlockChange }: SafetyChecksPanelProps) {
  const [checks, setChecks] = useState<SafetyCheck[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getSafetyChecks(rxId)
      .then((data) => {
        if (!active) return;
        setChecks(data);
        onBlockChange?.(data.some((c) => c.status === "block"));
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load safety checks.");
        onBlockChange?.(false);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [rxId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
      {/* header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[12px] font-bold uppercase tracking-wider text-slate-400">
          Automated Safety Checks
        </h2>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-600">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          live
        </span>
      </div>

      {/* legend */}
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
        <span className="flex items-center gap-1">
          <CheckCircleIcon width={12} height={12} className="text-emerald-500" /> ok
        </span>
        <span className="flex items-center gap-1">
          <AlertTriangleIcon width={12} height={12} className="text-amber-500" /> review
        </span>
        <span className="flex items-center gap-1">
          <AlertOctagonIcon width={12} height={12} className="text-red-500" /> immediate action
        </span>
      </div>

      {loading ? (
        <div className="space-y-2.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="rounded-lg border border-slate-100 p-3">
              <Skl w="60%" h={13} />
              <Skl w="90%" h={11} mt={8} />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12.5px] text-red-700">
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
              {s.tagLabel}
            </span>
          </div>
          {expandable && (
            <p className={`mt-1 text-[12.5px] leading-snug ${s.detailClass}`}>{check.message}</p>
          )}
          {open && check.details && (
            <p className="mono mt-1.5 text-[11px] text-slate-500">{check.details}</p>
          )}
          {expandable && (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              className={`mt-1.5 flex items-center gap-0.5 text-[11.5px] font-semibold ${s.iconClass}`}
            >
              Details{" "}
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
