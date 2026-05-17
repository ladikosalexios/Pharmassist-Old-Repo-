import { useEffect, useState } from "react";
import { AlertTriangleIcon, FileTextIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import {
  listPharmacies,
  seedDemoData,
  type DemoSeedResult,
  type Pharmacy,
} from "../../lib/adminApi";

export function AdminDemoData() {
  const { toast } = useToast();
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [pharmacyId, setPharmacyId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<DemoSeedResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPharmacies({ active: true, limit: 200 })
      .then((res) => setPharmacies(res.items))
      .catch(() => setPharmacies([]));
  }, []);

  async function onSeed() {
    if (!pharmacyId) return;
    const confirmed = window.confirm(
      "Insert synthetic demo records into this pharmacy? Use this only on test/demo pharmacies.",
    );
    if (!confirmed) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await seedDemoData(pharmacyId);
      setResult(res);
      toast("Demo data seeded", "success");
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Could not seed demo data.";
      setError(message);
      toast(message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-bold text-slate-900">Demo Data</h1>
        <p className="mt-1 text-sm text-slate-500">
          Seed a pharmacy with synthetic clinical records for demos and testing.
        </p>
      </div>

      <div className="card p-5 sm:p-6">
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangleIcon width={16} height={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Non-production tooling</div>
            <p className="mt-0.5">
              This inserts synthetic patient conditions, ADR reports, and documentation-log rows
              into the selected pharmacy. Use it only on test/demo pharmacies. Re-running adds
              another set of records (no de-duplication).
            </p>
          </div>
        </div>

        <div className="mt-5 max-w-md">
          <label
            htmlFor="demo-pharmacy"
            className="mb-1.5 block text-[13px] font-medium text-slate-600"
          >
            Pharmacy
          </label>
          <select
            id="demo-pharmacy"
            value={pharmacyId}
            onChange={(e) => setPharmacyId(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          >
            <option value="">Select a pharmacy…</option>
            {pharmacies.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.city ? ` — ${p.city}` : ""}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4">
          <button
            type="button"
            onClick={onSeed}
            disabled={!pharmacyId || submitting}
            className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {submitting ? <span className="spinner" /> : <FileTextIcon />}
            {submitting ? "Seeding…" : "Seed sample data"}
          </button>
        </div>

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {result && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            <div className="font-semibold">Demo data seeded</div>
            <ul className="mt-1.5 space-y-0.5">
              <li>Patient conditions: {result.patient_conditions}</li>
              <li>ADR reports: {result.adr_reports}</li>
              <li>Documentation logs: {result.documentation_logs}</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
