import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircleIcon,
  ChevronRightIcon,
  ShieldIcon,
  ClockIcon,
  AlertTriangleIcon,
  PillIcon,
} from "./Icons";
import { ApiError, getActiveAlerts } from "../lib/api";
import type { ActiveAlert, AlertType, CheckStatus } from "../types";

type Severity = "Critical" | "Review";

interface StatusVisual {
  severity: Severity;
  border: string; // border + accent color
  bg: string; // soft background tint
  label: string; // text color for the type label
  pulse?: boolean;
}

// Severity styling is driven by the check's STATUS (block vs review), not its
// type — a review-level interaction must not look like a hard block. The check
// type only selects the icon.
const STATUS_VISUAL: Record<CheckStatus, StatusVisual> = {
  block: {
    severity: "Critical",
    border: "border-red-300",
    bg: "bg-red-50",
    label: "text-red-700",
    pulse: true,
  },
  review: {
    severity: "Review",
    border: "border-amber-300",
    bg: "bg-amber-50",
    label: "text-amber-700",
  },
  // Never rendered (the dashboard only surfaces non-OK alerts) — defined for
  // exhaustiveness so the map is total over CheckStatus.
  ok: {
    severity: "Review",
    border: "border-slate-200",
    bg: "bg-slate-50",
    label: "text-slate-600",
  },
};

const TYPE_ICON: Record<AlertType, typeof PillIcon> = {
  interactions: PillIcon,
  contraindications: AlertTriangleIcon,
  duplicate_therapy: ClockIcon,
  dose_validation: AlertTriangleIcon,
  pregnancy: ClockIcon,
  G6PD: ShieldIcon,
};

const SEVERITY_COLOR: Record<Severity, string> = {
  Critical: "text-red-600",
  Review: "text-amber-600",
};

interface SafetyAlertsPanelProps {
  /** Cap the visible scroll area; defaults to 24rem. */
  maxHeightClass?: string;
  /** Header title; defaults to "Safety Alerts". The Counter overrides this
   * to "Active safety alerts" (the wording the redesign reference uses). */
  title?: string;
}

export function SafetyAlertsPanel({
  maxHeightClass = "max-h-96",
  title = "Safety Alerts",
}: SafetyAlertsPanelProps) {
  const [alerts, setAlerts] = useState<ActiveAlert[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // IDs we've already animated in — used so refetches only animate genuinely new alerts.
  const seenIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getActiveAlerts()
      .then((data) => {
        if (active) setAlerts(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load active alerts.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const counts = countSeverities(alerts ?? []);

  return (
    <section className="card overflow-hidden">
      <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
        <ShieldIcon width={16} height={16} className="text-slate-500" />
        <h3 className="text-[13.5px] font-bold text-slate-900">{title}</h3>
        {alerts && alerts.length > 0 && (
          <span className="ml-auto rounded-full bg-red-50 px-2 py-0.5 text-[11.5px] font-semibold text-red-700">
            {alerts.length}
          </span>
        )}
      </header>

      {loading ? (
        <div className="flex items-center gap-2 px-5 py-6 text-sm text-slate-500">
          <span className="spinner text-brand-600" /> Loading alerts…
        </div>
      ) : error ? (
        <div className="m-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : !alerts || alerts.length === 0 ? (
        <div className="px-5 py-8 text-center text-sm text-slate-500">No active alerts.</div>
      ) : (
        <div className={`space-y-3 overflow-y-auto p-4 ${maxHeightClass}`}>
          {alerts.map((a) => {
            const isNew = !seenIds.current.has(a.id);
            seenIds.current.add(a.id);
            return <AlertCard key={a.id} alert={a} isNew={isNew} />;
          })}
        </div>
      )}

      <footer className="border-t border-slate-200 bg-slate-50 px-5 py-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Alert Summary
        </div>
        <ul className="space-y-1 text-xs">
          <SummaryRow label="Critical" count={counts.Critical} color={SEVERITY_COLOR.Critical} />
          <SummaryRow label="Review" count={counts.Review} color={SEVERITY_COLOR.Review} />
        </ul>
      </footer>
    </section>
  );
}

function AlertCard({ alert, isNew }: { alert: ActiveAlert; isNew: boolean }) {
  const v = STATUS_VISUAL[alert.status] ?? STATUS_VISUAL.review;
  const Icon = TYPE_ICON[alert.type] ?? AlertTriangleIcon;
  return (
    <article
      className={`rounded-xl border-2 ${v.border} ${v.bg} p-3.5 ${isNew ? "animate-alert-in" : ""} ${v.pulse ? "animate-pulse-red-border" : ""}`}
      role="listitem"
    >
      <div className="flex items-center gap-1.5">
        <Icon width={14} height={14} className={v.label} />
        <span className={`text-xs font-bold tracking-wide ${v.label}`}>
          {alert.type.toUpperCase()}
        </span>
        <span className="ml-auto text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {v.severity}
        </span>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-slate-700">{alert.description}</p>
      {alert.rxId && (
        <Link
          to={`/prescription/${alert.rxId}`}
          className="mt-2 inline-flex items-center gap-1 text-[12px] font-semibold text-brand-600 hover:underline"
        >
          View Prescription <ChevronRightIcon width={12} height={12} />
        </Link>
      )}
    </article>
  );
}

function SummaryRow({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <li className="flex items-center justify-between">
      <span className={`font-semibold ${color}`}>{label}</span>
      <span className={`font-bold ${color}`}>{count}</span>
    </li>
  );
}

function countSeverities(alerts: ActiveAlert[]): Record<Severity, number> {
  const out: Record<Severity, number> = { Critical: 0, Review: 0 };
  for (const a of alerts) {
    const sev = STATUS_VISUAL[a.status]?.severity;
    if (sev) out[sev]++;
  }
  return out;
}
