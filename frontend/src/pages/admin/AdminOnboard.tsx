import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ChevronLeftIcon, AlertCircleIcon, CheckCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import { onboardPharmacy, type PharmacyCreate } from "../../lib/adminApi";

interface FormState {
  pharmacist_email: string;
  name: string;
  pharmapi_unit_id: string;
  address: string;
  street_name: string;
  street_number: string;
  area: string;
  city: string;
  postal_code: string;
  phone: string;
  fax: string;
  email: string;
  geographic_region: string;
  accounting_category: string;
  tax_id: string;
  is_branch: boolean;
}

const EMPTY: FormState = {
  pharmacist_email: "",
  name: "",
  pharmapi_unit_id: "",
  address: "",
  street_name: "",
  street_number: "",
  area: "",
  city: "",
  postal_code: "",
  phone: "",
  fax: "",
  email: "",
  geographic_region: "",
  accounting_category: "",
  tax_id: "",
  is_branch: false,
};

const PHARMACY_FIELDS: { key: keyof FormState; label: string; required?: boolean }[] = [
  { key: "name", label: "Pharmacy name", required: true },
  { key: "pharmapi_unit_id", label: "PharmAPI Unit ID", required: true },
  { key: "address", label: "Address" },
  { key: "street_name", label: "Street name" },
  { key: "street_number", label: "Street number" },
  { key: "area", label: "Area" },
  { key: "city", label: "City" },
  { key: "postal_code", label: "Postal code" },
  { key: "phone", label: "Phone" },
  { key: "fax", label: "Fax" },
  { key: "email", label: "Pharmacy email" },
  { key: "geographic_region", label: "Geographic region" },
  { key: "accounting_category", label: "Accounting category" },
  { key: "tax_id", label: "Tax ID" },
];

const INPUT_CLASS =
  "w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200";

export function AdminOnboard() {
  const { toast } = useToast();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setErr(null);
    const unit = Number(form.pharmapi_unit_id);
    if (
      !form.pharmacist_email.trim() ||
      !form.name.trim() ||
      !form.pharmapi_unit_id.trim() ||
      Number.isNaN(unit)
    ) {
      setErr("Pharmacist email, pharmacy name, and a numeric PharmAPI Unit ID are required.");
      return;
    }
    const pharmacy: PharmacyCreate = {
      name: form.name.trim(),
      pharmapi_unit_id: unit,
      address: form.address.trim() || null,
      street_name: form.street_name.trim() || null,
      street_number: form.street_number.trim() || null,
      area: form.area.trim() || null,
      city: form.city.trim() || null,
      postal_code: form.postal_code.trim() || null,
      phone: form.phone.trim() || null,
      fax: form.fax.trim() || null,
      email: form.email.trim() || null,
      geographic_region: form.geographic_region.trim() || null,
      accounting_category: form.accounting_category.trim() || null,
      tax_id: form.tax_id.trim() || null,
      is_branch: form.is_branch,
    };
    setSubmitting(true);
    try {
      const res = await onboardPharmacy(form.pharmacist_email.trim(), pharmacy);
      setInviteUrl(`${window.location.origin}${res.invite_url}`);
      toast("Pharmacy onboarded — invite created", "success");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not onboard the pharmacy.");
    } finally {
      setSubmitting(false);
    }
  }

  async function copyUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      toast("Invite link copied", "success");
    } catch {
      toast("Could not copy — select and copy the link manually.", "error");
    }
  }

  return (
    <div className="p-8">
      <Link
        to="/admin/pharmacies"
        className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-slate-500 hover:text-slate-900"
      >
        <ChevronLeftIcon width={16} height={16} /> All pharmacies
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Onboard a pharmacy</h1>
      <p className="mb-6 mt-1 text-sm text-slate-500">
        Create a new pharmacy and send an onboarding invite to its first pharmacist in one step.
      </p>

      {inviteUrl ? (
        <div className="card max-w-2xl p-6">
          <div className="mb-3 flex items-center gap-2 text-emerald-700">
            <CheckCircleIcon width={18} height={18} />
            <h2 className="text-sm font-semibold">Pharmacy onboarded</h2>
          </div>
          <p className="text-sm text-slate-600">
            Send this invite link to the pharmacist — there is no email delivery yet.
          </p>
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5">
            <div className="break-all font-mono text-[13px] text-emerald-900">{inviteUrl}</div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => copyUrl(inviteUrl)}
              className="btn bg-slate-900 text-white hover:bg-slate-800"
            >
              Copy link
            </button>
            <button
              type="button"
              onClick={() => {
                setForm(EMPTY);
                setInviteUrl(null);
              }}
              className="btn btn-outline"
            >
              Onboard another
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="card max-w-3xl p-6">
          {err && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{err}</span>
            </div>
          )}

          <label
            htmlFor="ob-pharmacist-email"
            className="mb-1.5 block text-[13px] font-medium text-slate-600"
          >
            Pharmacist email <span className="text-red-500">*</span>
          </label>
          <input
            id="ob-pharmacist-email"
            type="email"
            value={form.pharmacist_email}
            onChange={(e) => setForm((f) => ({ ...f, pharmacist_email: e.target.value }))}
            placeholder="pharmacist@example.gr"
            className={INPUT_CLASS}
          />

          <h2 className="mb-3 mt-6 text-sm font-semibold text-slate-900">Pharmacy details</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PHARMACY_FIELDS.map(({ key, label, required }) => (
              <div key={key}>
                <label
                  htmlFor={`ob-${key}`}
                  className="mb-1.5 block text-[13px] font-medium text-slate-600"
                >
                  {label}
                  {required && <span className="text-red-500"> *</span>}
                </label>
                <input
                  id={`ob-${key}`}
                  type="text"
                  value={form[key] as string}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className={INPUT_CLASS}
                />
              </div>
            ))}
            <label className="flex items-center gap-2 self-end pb-2.5 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.is_branch}
                onChange={(e) => setForm((f) => ({ ...f, is_branch: e.target.checked }))}
                className="h-4 w-4 rounded border-slate-300"
              />
              Branch location
            </label>
          </div>

          <div className="mt-5 flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? <span className="spinner" /> : null}
              {submitting ? "Onboarding…" : "Onboard pharmacy"}
            </button>
            <Link to="/admin/pharmacies" className="btn btn-outline">
              Cancel
            </Link>
          </div>
        </form>
      )}
    </div>
  );
}
