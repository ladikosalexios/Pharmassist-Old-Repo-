import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import { ContactPrescriberDrawer } from "../components/ContactPrescriberDrawer";
import { useToast } from "../components/Toast";
import { useKeyboardShortcuts } from "../lib/keyboard";
import {
  ApiError,
  getPrescription,
  getPatientConditions,
  createPatientCondition,
  deletePatientCondition,
  getSpc,
  verifySpcDocument,
} from "../lib/api";
import type { Medication, PatientCondition, Prescription, SpcDetails } from "../types";

// Patient factors ΗΔΥΚΑ does not report (age is auto-derived). Quick-captured on
// the review page so the safety checks can gate the drug's SPC lines by them.
const FACTOR_CODES = ["PREGNANCY", "RENAL_SEVERE", "HEPATIC", "G6PD"] as const;

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

/** Quick capture of patient factors ΗΔΥΚΑ doesn't report (pregnancy, renal,
 *  hepatic, G6PD). Each toggle writes/removes a patient_conditions row and asks
 *  the parent to refresh the safety checks, so a relevant SPC contraindication /
 *  precaution surfaces (or clears) immediately without a page reload. */
function FactorToggles({
  amka,
  conditions,
  onChanged,
}: {
  amka: string;
  conditions: PatientCondition[] | null;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<string | null>(null);
  const byCode = new Map((conditions ?? []).map((c) => [c.conditionCode, c] as const));

  async function toggle(code: string) {
    setBusy(code);
    try {
      const existing = byCode.get(code);
      if (existing) {
        await deletePatientCondition(amka, existing.id);
      } else {
        await createPatientCondition(amka, {
          conditionCode: code,
          name: t(`patientProfile.conditionCode${code}`),
        });
      }
      onChanged();
    } catch {
      // A failed toggle leaves the button as-is; the review page never errors.
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="col-span-2">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {t("review.factorsTitle")}
      </dt>
      <dd className="mt-1.5 flex flex-wrap gap-1.5">
        {FACTOR_CODES.map((code) => {
          const on = byCode.has(code);
          return (
            <button
              key={code}
              type="button"
              aria-pressed={on}
              disabled={busy === code}
              onClick={() => toggle(code)}
              className={`min-h-[32px] rounded-md border px-2.5 py-1 text-[12px] font-medium transition-colors disabled:opacity-50 ${
                on
                  ? "border-brand-300 bg-brand-100 text-brand-800 dark:border-brand-500/40 dark:bg-brand-500/20 dark:text-brand-200"
                  : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
              }`}
            >
              {t(`patientProfile.conditionCode${code}`)}
            </button>
          );
        })}
      </dd>
    </div>
  );
}

function PatientCard({
  rx,
  conditions,
  conditionsError,
  loading,
  onFactorsChanged,
}: {
  rx: Prescription | null;
  conditions: PatientCondition[] | null;
  conditionsError: string | null;
  loading: boolean;
  onFactorsChanged: () => void;
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
      {p.age != null && (
        <div className="mt-0.5 text-[13px] text-slate-500 dark:text-slate-400">
          {p.age} {t("review.yearsSuffix")}
        </div>
      )}
      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
        <Field label="AMKA" mono>
          {p.amka}
        </Field>
        {p.dateOfBirth && (
          <Field label={t("review.dateOfBirth")} mono>
            {p.dateOfBirth}
          </Field>
        )}
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
        {p.amka && (
          <FactorToggles amka={p.amka} conditions={conditions} onChanged={onFactorsChanged} />
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

/** Provenance badge for DB-backed SPC documents: amber "auto-extracted —
 *  verify against the source" until a pharmacist marks the document verified
 *  (green). Hidden for the mock fixture. The source link prefers the stable
 *  upstream URL and falls back to our stored PDF copy. */
function SpcProvenance({ spc, onChange }: { spc: SpcDetails; onChange: (v: boolean) => void }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  if (!spc.documentId || spc.source === "mock") return null;

  const href = spc.sourceUrl || `/spc/documents/${spc.documentId}/pdf`;
  const verified = Boolean(spc.verified);

  async function toggleVerified() {
    if (!spc.documentId) return;
    setBusy(true);
    try {
      const res = await verifySpcDocument(spc.documentId, !verified);
      onChange(res.verified);
    } catch {
      // Badge state simply stays as-is; the review page never errors on this.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium ${
        verified
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
          : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
      }`}
    >
      <span>{verified ? t("review.spcVerified") : t("review.spcAutoExtracted")}</span>
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="underline underline-offset-2 hover:opacity-80"
      >
        {t("review.spcSourceLink")}
      </a>
      {!verified && (
        <button
          type="button"
          onClick={toggleVerified}
          disabled={busy}
          className="ml-auto rounded border border-current px-1.5 py-0.5 text-[10.5px] font-semibold hover:opacity-80 disabled:opacity-50"
        >
          {t("review.spcMarkVerified")}
        </button>
      )}
    </div>
  );
}

/** SPC-derived guidance for one medicine: storage / in-use shelf life / disposal
 *  (§6.3-6.6) and food instructions (§4.2, shown only when the SPC has one).
 *  Precautions (§4.4) and contraindications (§4.3) are NOT shown here — they live
 *  in the safety-checks panel (patient-factor aware), so nothing repeats.
 *  Product-precise when the med carries its barcode (nhrn); drugs without SPC
 *  coverage render nothing. */
function SpcExtras({ atcCode, nhrn }: { atcCode?: string; nhrn?: string }) {
  const { t } = useTranslation();
  const [spc, setSpc] = useState<SpcDetails | null>(null);

  useEffect(() => {
    if (!atcCode) return;
    let active = true;
    getSpc(atcCode, nhrn)
      .then((data) => {
        if (active) setSpc(data);
      })
      .catch(() => {
        // Partial SPC coverage is expected — a missing SPC just means no
        // extras section, never an error state on the review page.
      });
    return () => {
      active = false;
    };
  }, [atcCode, nhrn]);

  if (!spc) return null;
  const storage = spc.storage;
  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4 dark:border-slate-800">
      <SpcProvenance
        spc={spc}
        onChange={(v) => setSpc((cur) => (cur ? { ...cur, verified: v } : cur))}
      />
      {storage && (
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {t("review.storageTitle")}
          </dt>
          <dd className="mt-1 text-[12.5px] leading-snug text-slate-700 dark:text-slate-300">
            {storage.conditions}
          </dd>
          {storage.afterOpening && (
            <dd className="mt-1.5 rounded-lg bg-slate-50 p-2.5 text-[12.5px] leading-snug text-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
              <span className="font-semibold">{t("review.afterOpening")}: </span>
              {storage.afterOpening}
            </dd>
          )}
          {storage.disposal && (
            <dd className="mt-1.5 text-[12px] leading-snug text-slate-500 dark:text-slate-400">
              <span className="font-semibold">{t("review.disposal")}: </span>
              {storage.disposal}
            </dd>
          )}
        </div>
      )}

      {spc.foodInstructions && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-500/25 dark:bg-emerald-500/10">
          <div className="text-[11px] font-bold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
            {t("review.foodInstructions")}
          </div>
          <p className="mt-1 text-[12.5px] leading-snug text-emerald-800 dark:text-emerald-200">
            {spc.foodInstructions}
          </p>
        </div>
      )}
    </div>
  );
}

function MedicationCard({
  med,
  index,
  total,
}: {
  med: Partial<Medication>;
  index: number;
  total: number;
}) {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
      <CardHead>
        {total > 1 ? t("review.medicationOf", { n: index, total }) : t("review.medication")}
      </CardHead>
      <div className="text-[16px] font-bold leading-snug text-slate-900 dark:text-slate-100">
        {med.drugName}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-slate-500 dark:text-slate-400">
        {med.atcCode && (
          <span className="mono rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            ATC {med.atcCode}
          </span>
        )}
        {med.nhrn && (
          <span className="mono rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {t("review.nhrnLabel")} {med.nhrn}
          </span>
        )}
      </div>
      {(med.dose || med.form || med.route || med.frequency || med.treatmentDuration) && (
        <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
          {med.dose && <Field label={t("review.dose")}>{med.dose}</Field>}
          {med.form && <Field label={t("review.form")}>{med.form}</Field>}
          {med.route && <Field label={t("review.route")}>{med.route}</Field>}
          {med.frequency && <Field label={t("review.frequency")}>{med.frequency}</Field>}
          {med.treatmentDuration && (
            <Field label={t("review.duration")}>{med.treatmentDuration}</Field>
          )}
        </dl>
      )}
      <SpcExtras atcCode={med.atcCode} nhrn={med.nhrn} />
    </div>
  );
}

function MedicationColumn({ rx, loading }: { rx: Prescription | null; loading: boolean }) {
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

  // Multi-medicine prescriptions carry every therapy line in `medications`;
  // single-med prescriptions fall back to the legacy `medication` object.
  const meds: Partial<Medication>[] = rx.medications?.length ? rx.medications : [rx.medication];
  const d = rx.prescriber;
  return (
    <div className="flex flex-col gap-5">
      {meds.map((m, i) => (
        <MedicationCard key={m.nhrn ?? m.atcCode ?? i} med={m} index={i + 1} total={meds.length} />
      ))}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
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
  const { toast } = useToast();
  const { t } = useTranslation();
  const [rx, setRx] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [flagOpen, setFlagOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [conditions, setConditions] = useState<PatientCondition[] | null>(null);
  const [conditionsError, setConditionsError] = useState<string | null>(null);
  // Bumped when a factor toggle changes conditions, to re-fetch the safety card.
  const [checksRefresh, setChecksRefresh] = useState(0);

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

  const amka = rx?.patient?.amka;
  const loadConditions = useCallback(() => {
    if (!amka) return;
    setConditionsError(null);
    getPatientConditions(amka)
      .then(setConditions)
      .catch((e: unknown) =>
        setConditionsError(e instanceof ApiError ? e.message : t("review.couldNotLoadConditions")),
      );
  }, [amka, t]);

  useEffect(() => {
    loadConditions();
  }, [loadConditions]);

  // A factor toggle: reload the conditions chips AND re-run the safety checks so
  // a newly-relevant SPC contraindication / precaution appears (or clears) live.
  const handleFactorsChanged = useCallback(() => {
    loadConditions();
    setChecksRefresh((n) => n + 1);
  }, [loadConditions]);

  useKeyboardShortcuts({
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
          onFactorsChanged={handleFactorsChanged}
        />
        <MedicationColumn rx={rx} loading={loading} />
        <SafetyChecksPanel
          rxId={rxId}
          checks={rx?.safetyChecks ?? null}
          refreshKey={checksRefresh}
        />
      </div>
    </div>
  );
}
