import { useEffect, useState } from "react";
import {
  CheckCircleIcon,
  AlertTriangleIcon,
  AlertOctagonIcon,
  AlertCircleIcon,
  ChevronRightIcon,
} from "./Icons";
import { ApiError, getSafetyChecks } from "../lib/api";
import type { CheckStatus, SafetyCheck } from "../types";

interface Tone {
  Icon: typeof CheckCircleIcon;
  iconClass: string;
  rowBg: string;
  border: string;
  label: string;
}

const TONE: Record<CheckStatus, Tone> = {
  ok: {
    Icon: CheckCircleIcon,
    iconClass: "text-emerald-600",
    rowBg: "bg-emerald-50",
    border: "border-emerald-200",
    label: "No issues detected",
  },
  review: {
    Icon: AlertTriangleIcon,
    iconClass: "text-amber-600",
    rowBg: "bg-amber-50",
    border: "border-amber-200",
    label: "Review required",
  },
  block: {
    Icon: AlertOctagonIcon,
    iconClass: "text-red-600",
    rowBg: "bg-red-50",
    border: "border-red-200",
    label: "Immediate action required",
  },
};

interface SafetyChecksPanelProps {
  rxId: string;
}

export function SafetyChecksPanel({ rxId }: SafetyChecksPanelProps) {
  const [checks, setChecks] = useState<SafetyCheck[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setExpandedId(null);
    getSafetyChecks(rxId)
      .then((data) => {
        if (active) setChecks(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load safety checks.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [rxId]);

  return (
    <section className="card overflow-hidden">
      <header className="border-b border-slate-200 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-900">Automated Safety Checks</h2>
        <p className="mt-0.5 text-xs text-slate-500">Real-time clinical decision support</p>
      </header>

      {loading ? (
        <div className="flex items-center gap-2 px-5 py-6 text-sm text-slate-500">
          <span className="spinner text-brand-600" /> Running safety checks…
        </div>
      ) : error ? (
        <div className="m-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : (
        <ul className="divide-y divide-slate-100">
          {checks?.map((c) => (
            <CheckRow
              key={c.id}
              check={c}
              isExpanded={expandedId === c.id}
              onToggle={() => setExpandedId((id) => (id === c.id ? null : c.id))}
            />
          ))}
        </ul>
      )}

      <footer className="border-t border-slate-200 bg-slate-50 px-5 py-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Status Legend
        </div>
        <ul className="space-y-1.5 text-xs text-slate-700">
          <li className="flex items-center gap-2">
            <CheckCircleIcon width={14} height={14} className="text-emerald-600" /> Circle — No
            issues detected
          </li>
          <li className="flex items-center gap-2">
            <AlertTriangleIcon width={14} height={14} className="text-amber-600" /> Triangle —
            Review required
          </li>
          <li className="flex items-center gap-2">
            <AlertOctagonIcon width={14} height={14} className="text-red-600" /> Octagon — Immediate
            action
          </li>
        </ul>
      </footer>
    </section>
  );
}

function CheckRow({
  check,
  isExpanded,
  onToggle,
}: {
  check: SafetyCheck;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const tone = TONE[check.status];
  const expandable = check.status !== "ok";

  const headerContent = (
    <>
      <tone.Icon width={18} height={18} className={`mt-0.5 shrink-0 ${tone.iconClass}`} />
      <div className="min-w-0 flex-1 text-left">
        <div className={`text-xs font-bold ${tone.iconClass}`}>{tone.label}</div>
        <div className="mt-0.5 text-sm font-semibold text-slate-900">{check.name}</div>
        <p className="mt-1 text-[13px] text-slate-600">{check.message}</p>
      </div>
      {expandable && (
        <ChevronRightIcon
          width={16}
          height={16}
          className={`mt-1 shrink-0 text-slate-400 transition-transform ${isExpanded ? "rotate-90" : ""}`}
        />
      )}
    </>
  );

  return (
    <li className={tone.rowBg}>
      {expandable ? (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isExpanded}
          aria-controls={`check-body-${check.id}`}
          className="flex w-full items-start gap-3 px-5 py-4 text-left hover:bg-black/[0.02] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-200"
        >
          {headerContent}
        </button>
      ) : (
        <div className="flex items-start gap-3 px-5 py-4">{headerContent}</div>
      )}

      {expandable && isExpanded && (
        <div id={`check-body-${check.id}`} className={`border-t ${tone.border} px-5 py-4`}>
          {check.details && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Full details
              </div>
              <p className="mt-1 text-[13px] leading-relaxed text-slate-700">{check.details}</p>
            </div>
          )}
          {check.recommendedAction && (
            <div className="mt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Recommended action
              </div>
              <p
                className={`mt-1 rounded-md border ${tone.border} bg-white p-3 text-[13px] leading-relaxed text-slate-700`}
              >
                {check.recommendedAction}
              </p>
            </div>
          )}
          {!check.details && !check.recommendedAction && (
            <p className="text-[13px] text-slate-500">No additional details available.</p>
          )}
        </div>
      )}
    </li>
  );
}
