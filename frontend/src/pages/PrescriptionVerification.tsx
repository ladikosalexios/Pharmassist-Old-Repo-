import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeftIcon,
  PhoneIcon,
  FlagIcon,
  ChevronRightIcon,
  AlertCircleIcon,
} from "../components/Icons";
import { SafetyChecksPanel } from "../components/SafetyChecksPanel";
import { FlagDiscrepancyModal } from "../components/FlagDiscrepancyModal";
import { DispenseWizard } from "../components/DispenseWizard";
import { ContactPrescriberDrawer } from "../components/ContactPrescriberDrawer";
import { useToast } from "../components/Toast";
import { useKeyboardShortcuts } from "../lib/keyboard";
import { ApiError, getPrescription, getPatientConditions } from "../lib/api";
import type { Prescription, PatientCondition } from "../types";

function Skl({ w = "100%", h = 14, mt = 0 }: { w?: string; h?: number; mt?: number }) {
  return (
    <div className="sk animate-shimmer rounded" style={{ width: w, height: h, marginTop: mt }} />
  );
}

function CardHead({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h2 className="text-[12px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
        {children}
      </h2>
    </div>
  );
}

function Field({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {label}
      </dt>
      <dd
        className={`mt-0.5 text-[13.5px] text-slate-800 dark:text-slate-200 ${mono ? "mono" : ""}`}
      >
        {children}
      </dd>
    </div>
  );
}

function PatientCard({
  rx,
  conditions,
  conditionsError,
  loading,
}: {
  rx: Prescription | null;
  conditions: PatientCondition[] | null;
  conditionsError: string | null;
  loading: boolean;
}) {
  const { t } = useTranslation();
  if (loading || !rx) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <CardHead>{t("review.patient")}</CardHead>
        <Skl w="60%" h={20} />
        <Skl w="40%" h={13} mt={10} />
        <div className="mt-5 grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skl w="50%" h={10} />
              <Skl w="80%" h={14} mt={6} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const p = rx.patient;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
      <CardHead>{t("review.patient")}</CardHead>
      <div className="text-[18px] font-bold text-slate-900 dark:text-slate-100">{p.name}</div>
      <div className="mt-0.5 text-[13px] text-slate-500 dark:text-slate-400">
        {p.age} {t("review.yearsSuffix")}
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
        <Field label="AMKA" mono>
          {p.amka}
        </Field>
        <Field label={t("review.dateOfBirth")} mono>
          {p.dateOfBirth}
        </Field>
        {conditions && conditions.length > 0 && (
          <div className="col-span-2">
            <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              {t("review.conditions")}
            </dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {conditions.map((c) => (
                <span
                  key={c.id}
                  className="inline-flex items-center rounded-md border border-brand-100 bg-brand-50 px-2 py-0.5 text-[11.5px] font-medium text-brand-700 dark:border-brand-500/20 dark:bg-brand-500/15 dark:text-brand-300"
                >
                  {c.name}
                </span>
              ))}
            </dd>
          </div>
        )}
        {conditionsError && (
          <div className="col-span-2 flex items-center gap-1 text-[12px] text-red-600 dark:text-red-400">
            <AlertCircleIcon width={13} height={13} className="shrink-0" />
            {conditionsError}
          </div>
        )}
        {p.allergies && (
          <div className="col-span-2">
            <Field label={t("review.allergies")}>{p.allergies}</Field>
          </div>
        )}
      </dl>
      <Link
        to={`/patients/${p.amka}?from=${encodeURIComponent(rx.rxId)}`}
        className="mt-4 inline-flex items-center gap-0.5 text-[12.5px] font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
      >
        {t("review.viewFullPatientProfile")} <ChevronRightIcon width={14} height={14} />
      </Link>
    </div>
  );
}

function MedicationCard({ rx, loading }: { rx: Prescription | null; loading: boolean }) {
  const { t } = useTranslation();
  if (loading || !rx) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <CardHead>{t("review.medication")}</CardHead>
        <Skl w="90%" h={18} />
        <Skl w="50%" h={13} mt={10} />
        <div className="mt-5 grid grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i}>
              <Skl w="50%" h={10} />
              <Skl w="75%" h={14} mt={6} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const m = rx.medication;
  const d = rx.prescriber;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
      <CardHead>{t("review.medication")}</CardHead>
      <div className="text-[16px] font-bold leading-snug text-slate-900 dark:text-slate-100">
        {m.drugName}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-slate-500 dark:text-slate-400">
        {m.atcCode && (
          <span className="mono rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            ATC {m.atcCode}
          </span>
        )}
        {m.nhrn && (
          <span className="mono rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {t("review.nhrnLabel")} {m.nhrn}
          </span>
        )}
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
        <Field label={t("review.dose")}>{m.dose}</Field>
        <Field label={t("review.form")}>{m.form}</Field>
        <Field label={t("review.route")}>{m.route}</Field>
        <Field label={t("review.frequency")}>{m.frequency}</Field>
        <Field label={t("review.duration")}>{m.treatmentDuration}</Field>
      </dl>
      <div className="mt-5 border-t border-slate-100 pt-4 dark:border-slate-800">
        <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          {t("review.prescriber")}
        </dt>
        <div className="mt-1 text-[13.5px] font-semibold text-slate-800 dark:text-slate-200">
          {d.name}
        </div>
        <div className="mt-0.5 text-[12.5px] text-slate-500 dark:text-slate-400">
          {d.specialty} · <span className="mono">{d.licenceId}</span>
        </div>
        {d.contact && (
          <a
            href={`tel:${d.contact}`}
            className="mono mt-0.5 block text-[12.5px] text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
          >
            {d.contact}
          </a>
        )}
      </div>
    </div>
  );
}

export function PrescriptionVerification() {
  const { rxId = "" } = useParams<{ rxId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation();
  const [rx, setRx] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [flagOpen, setFlagOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [hasBlock, setHasBlock] = useState(false);
  const [checksLoading, setChecksLoading] = useState(true);
  const [conditions, setConditions] = useState<PatientCondition[] | null>(null);
  const [conditionsError, setConditionsError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    getPrescription(rxId)
      .then((data) => {
        if (active) setRx(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        if (e instanceof ApiError) setLoadError(e.message);
        else setLoadError(t("review.cannotLoadPrescription"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rxId]);

  useEffect(() => {
    if (!rx?.patient?.amka) return;
    let active = true;
    setConditionsError(null);
    getPatientConditions(rx.patient.amka)
      .then((data) => {
        if (active) setConditions(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setConditionsError(e instanceof ApiError ? e.message : t("review.couldNotLoadConditions"));
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rx?.patient?.amka]);

  function onClickApprove() {
    if (!rx) return;
    if (hasBlock) return;
    setApproveOpen(true);
  }

  function onDispensed(status: string) {
    if (!rx) return;
    setRx({ ...rx, status });
    toast(t("review.prescriptionApprovedRecorded"), "success");
  }

  const handleWizardClose = useCallback(() => {
    setApproveOpen(false);
    if (rx?.status === "COMPLETED") navigate("/dashboard");
  }, [rx?.status, navigate]);

  useKeyboardShortcuts({
    c: () => {
      if (!rx) return;
      if (rx.status === "COMPLETED") {
        toast(t("review.prescriptionAlreadyCompleted"), "info");
        return;
      }
      if (rx.status === "FLAGGED") {
        toast(t("review.prescriptionFlaggedClearFirst"), "info");
        return;
      }
      onClickApprove();
    },
    f: () => {
      if (!rx) return;
      if (rx.status === "FLAGGED") {
        toast(t("review.prescriptionAlreadyFlagged"), "info");
        return;
      }
      if (rx.status === "COMPLETED") {
        toast(t("review.prescriptionAlreadyCompleted"), "info");
        return;
      }
      setFlagOpen(true);
    },
  });

  if (loadError) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <Link
          to="/dashboard"
          className="mb-4 inline-flex min-h-[40px] items-center gap-1.5 text-[13px] font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ArrowLeftIcon width={15} height={15} /> {t("review.backToCounter")}
        </Link>
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-500/30 dark:bg-red-500/10">
          <div className="flex items-start gap-2 text-red-700 dark:text-red-400">
            <AlertCircleIcon className="mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold">
                {t("review.couldNotLoadPrescriptionId", { rxId })}
              </div>
              <p className="mt-1 text-sm text-red-600 dark:text-red-400/90">{loadError}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isCompleted = rx?.status === "COMPLETED";
  const isFlagged = rx?.status === "FLAGGED";
  const approveDisabled = loading || checksLoading || hasBlock || isCompleted || isFlagged;

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-6 sm:px-6 lg:px-8">
      {/* back link */}
      <Link
        to="/dashboard"
        className="inline-flex min-h-[40px] items-center gap-1.5 text-[13px] font-medium text-slate-500 transition-colors hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
      >
        <ArrowLeftIcon width={15} height={15} /> {t("review.backToCounter")}
      </Link>

      {/* header row */}
      <div className="mt-3 flex flex-col gap-4 border-b border-slate-200 pb-5 dark:border-slate-800 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-[24px] font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {t("review.reviewPrescription")}
          </h1>
          {rx && (
            <div className="mono mt-1 text-[13px] text-slate-500 dark:text-slate-400">
              {rx.code}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setContactOpen(true)}
            disabled={!rx}
            className="flex min-h-[40px] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[13px] font-semibold text-slate-700 shadow-card transition-colors hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            <PhoneIcon width={15} height={15} /> {t("review.contactPrescriber")}
          </button>

          <button
            type="button"
            onClick={() => setFlagOpen(true)}
            disabled={!rx || isCompleted || isFlagged}
            className="flex min-h-[40px] items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2 text-[13px] font-semibold text-amber-700 shadow-card transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400 dark:hover:bg-amber-500/20"
          >
            <FlagIcon width={15} height={15} />{" "}
            {isFlagged ? t("review.flagged") : t("review.flagDiscrepancy")}
          </button>

          <div className="group relative">
            <button
              type="button"
              onClick={onClickApprove}
              disabled={approveDisabled}
              className={`flex min-h-[40px] items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold shadow-card transition-colors ${
                approveDisabled
                  ? "cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
                  : "bg-brand-600 text-white hover:bg-brand-700 dark:hover:bg-brand-500"
              }`}
            >
              {isCompleted ? t("review.completed") : t("review.approveAndDispense")}
              <ChevronRightIcon width={15} height={15} />
            </button>
            {hasBlock && (
              <div className="pointer-events-none absolute right-0 top-full z-10 mt-2 w-64 rounded-lg bg-slate-900 px-3 py-2 text-[12px] leading-snug text-white opacity-0 shadow-cardLg transition-opacity group-hover:opacity-100 dark:bg-slate-700">
                {t("review.resolveCriticalAlerts")}
                <span className="absolute -top-1 right-6 h-2 w-2 rotate-45 bg-slate-900 dark:bg-slate-700" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* dialogs */}
      {rx && (
        <>
          <FlagDiscrepancyModal
            rxId={rx.rxId}
            open={flagOpen}
            onClose={() => setFlagOpen(false)}
            onFlagged={(status) => setRx((cur) => (cur ? { ...cur, status } : cur))}
          />
          <DispenseWizard
            open={approveOpen}
            rxId={rx.rxId}
            barcode={rx.code}
            nhrn={rx.medication.nhrn}
            patientName={rx.patient.name}
            drugName={rx.medication.drugName}
            onClose={handleWizardClose}
            onDispensed={onDispensed}
          />
          <ContactPrescriberDrawer
            open={contactOpen}
            rxId={rx.rxId}
            patientName={rx.patient.name}
            prescriber={rx.prescriber}
            onClose={() => setContactOpen(false)}
          />
        </>
      )}

      {/* 3-column grid */}
      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[1.35fr_1fr_1.05fr]">
        <PatientCard
          rx={rx}
          conditions={conditions}
          conditionsError={conditionsError}
          loading={loading}
        />
        <MedicationCard rx={rx} loading={loading} />
        <SafetyChecksPanel
          rxId={rxId}
          onBlockChange={setHasBlock}
          onLoadingChange={setChecksLoading}
        />
      </div>
    </div>
  );
}
