import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ChevronLeftIcon,
  PhoneIcon,
  FlagIcon,
  CheckIcon,
  AlertCircleIcon,
  AlertOctagonIcon,
  FileTextIcon,
} from "../components/Icons";
import { SafetyChecksPanel } from "../components/SafetyChecksPanel";
import { SPCQuickReference } from "../components/SPCQuickReference";
import { PrescriptionDetailsCard } from "../components/PrescriptionDetailsCard";
import { FlagDiscrepancyModal } from "../components/FlagDiscrepancyModal";
import { ApproveConfirmModal } from "../components/ApproveConfirmModal";
import { ContactPrescriberDrawer } from "../components/ContactPrescriberDrawer";
import { useToast } from "../components/Toast";
import { useKeyboardShortcuts } from "../lib/keyboard";
import { ApiError, getPrescription, approvePrescription } from "../lib/api";
import type { Prescription } from "../types";

export function PrescriptionVerification() {
  const { rxId = "" } = useParams<{ rxId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [rx, setRx] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<{ kind: "ok" | "warn" | "err"; text: string } | null>(
    null,
  );
  const [flagOpen, setFlagOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [approveSubmitting, setApproveSubmitting] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [blockedByChecks, setBlockedByChecks] = useState(false);

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
        else setLoadError("Cannot load prescription. Make sure the API is running.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [rxId]);

  function onClickApprove() {
    if (!rx) return;
    setActionMsg(null);
    const blockers = (rx.safetyChecks ?? []).filter((c) => c.status === "block");
    if (blockers.length > 0) {
      setBlockedByChecks(true);
      return;
    }
    setBlockedByChecks(false);
    setApproveError(null);
    setApproveOpen(true);
  }

  async function onConfirmApprove() {
    if (!rx) return;
    setApproveSubmitting(true);
    setApproveError(null);
    try {
      const result = await approvePrescription(rx.rxId);
      setRx({ ...rx, status: result.status });
      setApproveOpen(false);
      toast("Prescription approved and recorded", "success");
      navigate("/dashboard");
    } catch (e) {
      setApproveError(e instanceof ApiError ? e.message : "Approval failed. Please try again.");
    } finally {
      setApproveSubmitting(false);
    }
  }

  // Page-level keyboard shortcuts. The hook itself ignores keystrokes while
  // any modal/drawer is registered as open, so the C/F handlers don't fire
  // when the approve or flag dialogs are already up.
  useKeyboardShortcuts({
    c: () => {
      if (!rx) return;
      if (rx.status === "COMPLETED") {
        toast("Prescription is already completed.", "info");
        return;
      }
      if (rx.status === "FLAGGED") {
        toast("Prescription is flagged — clear the flag first.", "info");
        return;
      }
      onClickApprove();
    },
    f: () => {
      if (!rx) return;
      if (rx.status === "FLAGGED") {
        toast("Prescription is already flagged.", "info");
        return;
      }
      if (rx.status === "COMPLETED") {
        toast("Prescription is already completed.", "info");
        return;
      }
      setFlagOpen(true);
    },
  });

  if (loading) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-2 text-slate-500">
          <span className="spinner text-brand-600" /> Loading prescription…
        </div>
      </div>
    );
  }
  if (loadError || !rx) {
    return (
      <div className="p-8">
        <Link
          to="/dashboard"
          className="mb-4 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
        >
          <ChevronLeftIcon width={14} height={14} /> Back to Queue
        </Link>
        <div className="card p-6">
          <div className="flex items-start gap-2 text-red-700">
            <AlertCircleIcon className="mt-0.5" />
            <div>
              <div className="font-semibold">Could not load prescription {rxId}</div>
              <p className="mt-1 text-sm text-red-600">{loadError ?? "Unknown error."}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
          >
            <ChevronLeftIcon width={14} height={14} /> Back to Queue
          </button>
          <h1 className="mt-2 text-2xl font-bold text-slate-900">
            Prescription Verification
            <span className="ml-3 align-middle text-base font-mono font-medium text-slate-500">
              {rx.code}
            </span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => setContactOpen(true)} className="btn btn-outline">
            <PhoneIcon /> Contact Prescriber
          </button>
          {rx.status === "FLAGGED" ? (
            <button
              type="button"
              disabled
              aria-disabled="true"
              className="btn cursor-not-allowed border border-red-300 bg-red-50 text-red-700"
            >
              <FlagIcon /> Flagged
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setFlagOpen(true)}
              disabled={rx.status === "COMPLETED"}
              className="btn btn-amber disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <FlagIcon /> Flag Discrepancy
            </button>
          )}
          <button
            type="button"
            onClick={onClickApprove}
            disabled={rx.status === "COMPLETED" || rx.status === "FLAGGED"}
            className="btn btn-success disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <CheckIcon />
            {rx.status === "COMPLETED" ? "Completed" : "Approve Prescription"}
          </button>
          {rx.status === "COMPLETED" && (
            <Link
              to={`/instructions?rxId=${encodeURIComponent(rx.rxId)}`}
              className="btn btn-primary"
            >
              <FileTextIcon /> Generate Instructions
            </Link>
          )}
        </div>
      </div>

      <FlagDiscrepancyModal
        rxId={rx.rxId}
        open={flagOpen}
        onClose={() => setFlagOpen(false)}
        onFlagged={(status) => setRx((cur) => (cur ? { ...cur, status } : cur))}
      />

      <ApproveConfirmModal
        open={approveOpen}
        rxId={rx.rxId}
        patientName={rx.patient.name}
        drugName={rx.medication.drugName}
        dose={rx.medication.dose}
        submitting={approveSubmitting}
        error={approveError}
        onClose={() => {
          if (!approveSubmitting) setApproveOpen(false);
        }}
        onConfirm={onConfirmApprove}
      />

      <ContactPrescriberDrawer
        open={contactOpen}
        rxId={rx.rxId}
        patientName={rx.patient.name}
        prescriber={rx.prescriber}
        onClose={() => setContactOpen(false)}
      />

      {blockedByChecks && (
        <div
          role="alert"
          className="mb-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertOctagonIcon width={18} height={18} className="mt-0.5 shrink-0 text-red-600" />
          <div className="flex-1">
            <div className="font-semibold">Resolve all critical safety alerts before approving</div>
            <p className="mt-0.5 text-[13px] text-red-700">
              One or more automated safety checks require immediate action. Address them in the
              Safety Checks panel and try again.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setBlockedByChecks(false)}
            className="rounded p-1 text-red-700 hover:bg-red-100"
            aria-label="Dismiss"
          >
            <svg
              width={14}
              height={14}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {actionMsg && (
        <div
          className={`mb-5 rounded-lg border px-4 py-3 text-sm ${
            actionMsg.kind === "ok"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : actionMsg.kind === "warn"
                ? "border-amber-200 bg-amber-50 text-amber-800"
                : "border-red-200 bg-red-50 text-red-800"
          }`}
        >
          {actionMsg.text}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-10">
        {/* Left main column */}
        <div className="space-y-6 lg:col-span-7">
          <PatientInfoCard rx={rx} />
          <MedicationDetailsCard rx={rx} />
          <SPCQuickReference
            drugName={rx.medication.drugName}
            atcCode={rx.medication.atcCode ?? ""}
            fallback={{
              recommendedDosage: rx.medication.spcRecommendedDosage,
              contraindications: rx.spcQuickReference?.contraindications,
              majorInteractions: rx.spcQuickReference?.majorInteractions,
            }}
          />
        </div>

        {/* Right sticky column */}
        <div className="space-y-6 lg:col-span-3">
          <div className="lg:sticky lg:top-6 space-y-6">
            <SafetyChecksPanel rxId={rx.rxId} />
            <PrescriptionDetailsCard rx={rx} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="card overflow-hidden">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {action}
      </header>
      <div className="p-6">{children}</div>
    </section>
  );
}

function Field({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-sm text-slate-900 ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}

function PatientInfoCard({ rx }: { rx: Prescription }) {
  const p = rx.patient;
  return (
    <Section
      title="Patient Information"
      action={
        <Link
          to={`/patients/${p.amka}?from=${encodeURIComponent(rx.rxId)}`}
          className="text-sm font-medium text-brand-600 hover:underline"
        >
          View Full Patient Profile →
        </Link>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Name" value={p.name} />
        <Field label="Age" value={`${p.age} years`} />
        <Field label="Date of Birth" value={p.dateOfBirth} />
        <Field label="AMKA" value={p.amka} mono />
      </div>
      <div className="mt-5">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Medical Conditions
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {p.conditions.length ? (
            p.conditions.map((c) => (
              <span key={c} className="chip border border-brand-100 bg-brand-50 text-brand-700">
                {c}
              </span>
            ))
          ) : (
            <span className="text-sm text-slate-500">None recorded.</span>
          )}
        </div>
      </div>
      <div className="mt-5">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Allergies</div>
        <p className="mt-1 text-sm text-slate-900">{p.allergies || "None known."}</p>
      </div>
    </Section>
  );
}

function MedicationDetailsCard({ rx }: { rx: Prescription }) {
  const m = rx.medication;
  const d = rx.prescriber;
  return (
    <Section title="Medication Details">
      <div className="text-2xl font-bold text-slate-900">{m.drugName}</div>
      <div className="mt-1 text-sm text-slate-500">
        {m.dose} · {m.form} · {m.route}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Dose" value={m.dose} />
        <Field label="Form" value={m.form} />
        <Field label="Route" value={m.route} />
        <Field label="Frequency" value={m.frequency} />
        <Field label="Treatment Duration" value={m.treatmentDuration} />
        {m.atcCode && <Field label="ATC Code" value={m.atcCode} mono />}
      </div>

      <div className="mt-7 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Prescribing Physician
        </div>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name" value={d.name} />
          <Field label="Licence / ID" value={d.licenceId} mono />
          <Field label="Specialty" value={d.specialty} />
          <Field
            label="Contact"
            value={
              <a className="text-brand-600 hover:underline" href={`tel:${d.contact}`}>
                {d.contact}
              </a>
            }
          />
          <Field
            label="Email"
            value={
              <a className="text-brand-600 hover:underline" href={`mailto:${d.email}`}>
                {d.email}
              </a>
            }
          />
        </div>
      </div>
    </Section>
  );
}
