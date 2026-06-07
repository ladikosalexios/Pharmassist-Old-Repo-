import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { ApiError, getSpc } from "../lib/api";
import type { Prescription, SpcDetails } from "../types";

const STATUS_CHIP: Record<string, string> = {
  PENDING: "bg-amber-100 text-amber-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  FLAGGED: "bg-red-100 text-red-800",
};

const STATUS_LABEL_KEY: Record<string, string> = {
  PENDING: "rxDetails.statusPending",
  COMPLETED: "rxDetails.statusCompleted",
  FLAGGED: "rxDetails.statusFlagged",
};

interface PrescriptionDetailsCardProps {
  rx: Prescription;
}

export function PrescriptionDetailsCard({ rx }: PrescriptionDetailsCardProps) {
  const { t } = useTranslation();
  const [spc, setSpc] = useState<SpcDetails | null>(null);
  const atcCode = rx.medication.atcCode;

  useEffect(() => {
    if (!atcCode) return;
    let active = true;
    getSpc(atcCode)
      .then((data) => {
        if (active) setSpc(data);
      })
      .catch((e: unknown) => {
        // Non-fatal: card still renders the static SPC version from the
        // prescription. Surface in console only.
        if (e instanceof ApiError) console.warn("PrescriptionDetailsCard SPC fetch:", e.message);
      });
    return () => {
      active = false;
    };
  }, [atcCode]);

  const versionInfo = computeVersionInfo(rx.spcVersion, spc, rx.dateIssued, t);

  return (
    <section className="card p-5">
      <h2 className="mb-3 text-base font-semibold text-slate-900">{t("rxDetails.title")}</h2>
      <dl className="space-y-3">
        <Row
          label={t("rxDetails.prescriptionCode")}
          value={<span className="font-mono">{rx.code}</span>}
        />
        <Row label={t("rxDetails.dateIssued")} value={rx.dateIssued} />
        <Row
          label={t("rxDetails.status")}
          value={
            <span className={`chip ${STATUS_CHIP[rx.status] ?? "bg-slate-100 text-slate-800"}`}>
              {STATUS_LABEL_KEY[rx.status] ? t(STATUS_LABEL_KEY[rx.status]) : rx.status}
            </span>
          }
        />
        <Row
          label={t("rxDetails.spcVersion")}
          value={
            <span
              title={versionInfo.tooltip ?? undefined}
              className={
                versionInfo.outdated
                  ? "chip cursor-help bg-red-100 text-red-800"
                  : "text-sm text-slate-900"
              }
            >
              {versionInfo.label}
            </span>
          }
        />
      </dl>
    </section>
  );
}

interface VersionInfo {
  label: string;
  outdated: boolean;
  tooltip: string | null;
}

function computeVersionInfo(
  fallbackVersion: string | undefined,
  spc: SpcDetails | null,
  dateIssued: string,
  t: TFunction,
): VersionInfo {
  if (!spc) {
    return { label: fallbackVersion ?? "—", outdated: false, tooltip: null };
  }
  const updated = parseDate(spc.updatedAt);
  const issued = parseDate(dateIssued);
  const outdated = !!(updated && issued && updated.getTime() > issued.getTime());
  const dateLabel = updated ? formatDate(updated) : spc.updatedAt;
  return {
    label: `${spc.version} (${t("rxDetails.updatedLabel")}: ${dateLabel})`,
    outdated,
    tooltip: outdated ? t("rxDetails.outdatedTooltip") : null,
  };
}

function parseDate(value: string): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}

function formatDate(d: Date): string {
  // ISO yyyy-mm-dd to keep alignment with the existing UI.
  return d.toISOString().slice(0, 10);
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-2 last:border-b-0 last:pb-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="text-right text-sm text-slate-900">{value}</dd>
    </div>
  );
}
