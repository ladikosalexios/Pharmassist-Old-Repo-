import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ChevronLeftIcon, PhoneIcon, FlagIcon, CheckIcon, AlertCircleIcon, AlertOctagonIcon,
} from "../components/Icons";
import { SafetyChecksPanel } from "../components/SafetyChecksPanel";
import { FlagDiscrepancyModal } from "../components/FlagDiscrepancyModal";
import { ApproveConfirmModal } from "../components/ApproveConfirmModal";
import { ContactPrescriberDrawer } from "../components/ContactPrescriberDrawer";
import { useToast } from "../components/Toast";
import { ApiError, getPrescription, approvePrescription } from "../lib/api";
import type { Prescription } from "../types";

const STATUS_CHIP: Record<string, string> = {
  PENDING:   "bg-amber-100 text-amber-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  FLAGGED:   "bg-red-100 text-red-800",
};

export function PrescriptionVerification() {
  const { rxId = "" } = useParams<{ rxId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [rx, setRx] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<{ kind: "ok" | "warn" | "err"; text: string } | null>(null);
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
      .then((data) => { if (active) setRx(data); })
      .catch((e: unknown) => {
        if (!active) return;
        if (e instanceof ApiError) setLoadError(e.message);
        else setLoadError("Cannot load prescription. Make sure the API is running.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
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

  if (loading) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-2 text-slate-500"><span className="spinner text-brand-600" /> Loading prescription…</div>
      </div>
    );
  }
  if (loadError || !rx) {
    return (
      <div className="p-8">
        <Link to="/dashboard" className="mb-4 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline">
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
            <span className="ml-3 align-middle text-base font-mono font-medium text-slate-500">{rx.code}</span>
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
        onClose={() => { if (!approveSubmitting) setApproveOpen(false); }}
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
              One or more automated safety checks require immediate action. Address them in the Safety Checks panel and try again.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setBlockedByChecks(false)}
            className="rounded p-1 text-red-700 hover:bg-red-100"
            aria-label="Dismiss"
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {actionMsg && (
        <div
          className={`mb-5 rounded-lg border px-4 py-3 text-sm ${
            actionMsg.kind === "ok"   ? "border-emerald-200 bg-emerald-50 text-emerald-800" :
            actionMsg.kind === "warn" ? "border-amber-200 bg-amber-50 text-amber-800" :
                                        "border-red-200 bg-red-50 text-red-800"
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
          <SpcQuickReferenceCard rx={rx} />
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

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
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
        <button className="text-sm font-medium text-brand-600 hover:underline">View Full Patient Profile →</button>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Name" value={p.name} />
        <Field label="Age" value={`${p.age} years`} />
        <Field label="Date of Birth" value={p.dateOfBirth} />
        <Field label="AMKA" value={p.amka} mono />
      </div>
      <div className="mt-5">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Medical Conditions</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {p.conditions.length ? p.conditions.map((c) => (
            <span key={c} className="chip border border-brand-100 bg-brand-50 text-brand-700">{c}</span>
          )) : <span className="text-sm text-slate-500">None recorded.</span>}
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
    <Section
      title="Medication Details"
      action={<button className="text-sm font-medium text-brand-600 hover:underline">View Full SPC →</button>}
    >
      <div className="text-2xl font-bold text-slate-900">{m.drugName}</div>
      <div className="mt-1 text-sm text-slate-500">{m.dose} · {m.form} · {m.route}</div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Dose" value={m.dose} />
        <Field label="Form" value={m.form} />
        <Field label="Route" value={m.route} />
        <Field label="Frequency" value={m.frequency} />
        <Field label="Treatment Duration" value={m.treatmentDuration} />
      </div>

      <div className="mt-7 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Prescribing Physician</div>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name" value={d.name} />
          <Field label="Licence / ID" value={d.licenceId} mono />
          <Field label="Specialty" value={d.specialty} />
          <Field label="Contact" value={<a className="text-brand-600 hover:underline" href={`tel:${d.contact}`}>{d.contact}</a>} />
          <Field label="Email" value={<a className="text-brand-600 hover:underline" href={`mailto:${d.email}`}>{d.email}</a>} />
        </div>
      </div>

      <div className="mt-6">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">SPC Recommended Dosage</div>
        <p className="mt-2 rounded-lg bg-brand-50 p-4 text-sm text-slate-700">{m.spcRecommendedDosage}</p>
      </div>
    </Section>
  );
}

function SpcQuickReferenceCard({ rx }: { rx: Prescription }) {
  const s = rx.spcQuickReference;
  return (
    <Section title="SPC Quick Reference">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Key Contraindications</div>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
        {s.contraindications.map((c, i) => <li key={i}>{c}</li>)}
      </ul>

      <div className="mt-6 text-xs font-semibold uppercase tracking-wide text-slate-500">Major Interactions</div>
      <div className="mt-2 space-y-2">
        {s.majorInteractions.map((it, i) => (
          <div key={i} className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
            <span className="font-bold text-slate-900">{it.drug}</span>
            <span className="ml-2 text-amber-800">— {it.effect}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

function PrescriptionDetailsCard({ rx }: { rx: Prescription }) {
  return (
    <section className="card p-5">
      <h2 className="mb-3 text-base font-semibold text-slate-900">Prescription Details</h2>
      <dl className="space-y-3">
        <Row label="Prescription Code" value={<span className="font-mono">{rx.code}</span>} />
        <Row label="Date Issued" value={rx.dateIssued} />
        <Row label="Status" value={
          <span className={`chip ${STATUS_CHIP[rx.status] ?? "bg-slate-100 text-slate-800"}`}>
            {rx.status.charAt(0) + rx.status.slice(1).toLowerCase()}
          </span>
        } />
        <Row label="SPC Version" value={rx.spcVersion} />
      </dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-2 last:border-b-0 last:pb-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-900">{value}</dd>
    </div>
  );
}
