import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ChevronLeftIcon, PhoneIcon, FlagIcon, CheckIcon, AlertCircleIcon,
} from "../components/Icons";
import { SafetyChecksPanel } from "../components/SafetyChecksPanel";
import { ApiError, getPrescription, approvePrescription, flagPrescription } from "../lib/api";
import type { Prescription } from "../types";

const STATUS_CHIP: Record<string, string> = {
  PENDING:  "bg-amber-100 text-amber-800",
  APPROVED: "bg-emerald-100 text-emerald-800",
  FLAGGED:  "bg-red-100 text-red-800",
};

export function PrescriptionVerification() {
  const { rxId = "" } = useParams<{ rxId: string }>();
  const navigate = useNavigate();
  const [rx, setRx] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<{ kind: "ok" | "warn" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState<"approve" | "flag" | null>(null);
  const [showFlag, setShowFlag] = useState(false);
  const [flagReason, setFlagReason] = useState("");

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

  async function onApprove() {
    if (!rx || busy) return;
    setBusy("approve");
    setActionMsg(null);
    try {
      await approvePrescription(rx.rxId);
      setRx({ ...rx, status: "APPROVED" });
      setActionMsg({ kind: "ok", text: "Prescription approved." });
    } catch (e) {
      setActionMsg({ kind: "err", text: e instanceof ApiError ? e.message : "Approval failed." });
    } finally {
      setBusy(null);
    }
  }

  async function onConfirmFlag() {
    if (!rx || busy) return;
    if (!flagReason.trim()) return;
    setBusy("flag");
    setActionMsg(null);
    try {
      await flagPrescription(rx.rxId, flagReason.trim());
      setRx({ ...rx, status: "FLAGGED", flagReason: flagReason.trim() });
      setShowFlag(false);
      setFlagReason("");
      setActionMsg({ kind: "warn", text: "Prescription flagged for review." });
    } catch (e) {
      setActionMsg({ kind: "err", text: e instanceof ApiError ? e.message : "Flagging failed." });
    } finally {
      setBusy(null);
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
          <a href={`tel:${rx.prescriber.contact}`} className="btn btn-outline">
            <PhoneIcon /> Contact Prescriber
          </a>
          <button type="button" onClick={() => setShowFlag(true)} className="btn btn-amber">
            <FlagIcon /> Flag Discrepancy
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={busy !== null || rx.status === "APPROVED"}
            className="btn btn-success disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {busy === "approve" ? <span className="spinner" /> : <CheckIcon />}
            {rx.status === "APPROVED" ? "Approved" : "Approve Prescription"}
          </button>
        </div>
      </div>

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

      {showFlag && (
        <div className="mb-5 card p-5">
          <div className="mb-2 text-sm font-semibold text-slate-900">Flag this prescription</div>
          <p className="mb-3 text-xs text-slate-500">Describe the discrepancy. The prescriber will be notified.</p>
          <textarea
            value={flagReason}
            onChange={(e) => setFlagReason(e.target.value)}
            placeholder="e.g. Dose exceeds SPC recommendation; please clarify."
            className="w-full min-h-[80px] resize-vertical rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={onConfirmFlag}
              disabled={busy !== null || !flagReason.trim()}
              className="btn btn-amber disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {busy === "flag" ? <span className="spinner" /> : <FlagIcon />} Submit Flag
            </button>
            <button type="button" onClick={() => { setShowFlag(false); setFlagReason(""); }} className="btn btn-outline">
              Cancel
            </button>
          </div>
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
