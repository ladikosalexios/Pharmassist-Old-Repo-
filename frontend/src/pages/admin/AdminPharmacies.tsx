import { useEffect, useState, type FormEvent } from "react";
import { GridIcon, SearchIcon, FilterIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import {
  createPharmacy,
  listPharmacies,
  updatePharmacy,
  type Pharmacy,
  type PharmacyCreate,
} from "../../lib/adminApi";

interface FormState {
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

const TEXT_FIELDS: { key: keyof FormState; label: string; required?: boolean }[] = [
  { key: "name", label: "Name", required: true },
  { key: "pharmapi_unit_id", label: "PharmAPI Unit ID", required: true },
  { key: "address", label: "Address" },
  { key: "street_name", label: "Street name" },
  { key: "street_number", label: "Street number" },
  { key: "area", label: "Area" },
  { key: "city", label: "City" },
  { key: "postal_code", label: "Postal code" },
  { key: "phone", label: "Phone" },
  { key: "fax", label: "Fax" },
  { key: "email", label: "Email" },
  { key: "geographic_region", label: "Geographic region" },
  { key: "accounting_category", label: "Accounting category" },
  { key: "tax_id", label: "Tax ID" },
];

function toForm(p: Pharmacy): FormState {
  return {
    name: p.name,
    pharmapi_unit_id: String(p.pharmapi_unit_id),
    address: p.address ?? "",
    street_name: p.street_name ?? "",
    street_number: p.street_number ?? "",
    area: p.area ?? "",
    city: p.city ?? "",
    postal_code: p.postal_code ?? "",
    phone: p.phone ?? "",
    fax: p.fax ?? "",
    email: p.email ?? "",
    geographic_region: p.geographic_region ?? "",
    accounting_category: p.accounting_category ?? "",
    tax_id: p.tax_id ?? "",
    is_branch: p.is_branch,
  };
}

export function AdminPharmacies() {
  const { toast } = useToast();
  const [items, setItems] = useState<Pharmacy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Pharmacy | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  function reload() {
    setLoading(true);
    setError(null);
    listPharmacies({
      q: query || undefined,
      active: activeFilter === "" ? undefined : activeFilter === "true",
      limit: 200,
    })
      .then((res) => setItems(res.items))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load pharmacies."),
      )
      .finally(() => setLoading(false));
  }

  useEffect(reload, [query, activeFilter]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormErr(null);
    setShowForm(true);
  }

  function openEdit(p: Pharmacy) {
    setEditing(p);
    setForm(toForm(p));
    setFormErr(null);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormErr(null);
    const unit = Number(form.pharmapi_unit_id);
    if (!form.name.trim() || !form.pharmapi_unit_id.trim() || Number.isNaN(unit)) {
      setFormErr("Name and a numeric PharmAPI Unit ID are required.");
      return;
    }
    const payload: PharmacyCreate = {
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
      if (editing) {
        await updatePharmacy(editing.id, payload);
        toast("Pharmacy updated", "success");
      } else {
        await createPharmacy(payload);
        toast("Pharmacy created", "success");
      }
      closeForm();
      reload();
    } catch (e) {
      setFormErr(e instanceof ApiError ? e.message : "Could not save the pharmacy.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onToggle(p: Pharmacy) {
    setTogglingId(p.id);
    try {
      await updatePharmacy(p.id, { active: !p.active });
      toast(p.active ? "Pharmacy deactivated" : "Pharmacy activated", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not update the pharmacy.", "error");
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pharmacies</h1>
          <p className="mt-1 text-sm text-slate-500">
            Pharmacy accounts on the platform. Deactivating hides a pharmacy from new onboarding.
          </p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="btn bg-slate-900 text-white hover:bg-slate-800"
        >
          <GridIcon /> New Pharmacy
        </button>
      </div>

      {showForm && (
        <form onSubmit={onSubmit} className="card mb-5 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">
            {editing ? `Edit ${editing.name}` : "Create pharmacy"}
          </h2>
          {formErr && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{formErr}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {TEXT_FIELDS.map(({ key, label, required }) => (
              <div key={key}>
                <label
                  htmlFor={`ph-${key}`}
                  className="mb-1.5 block text-[13px] font-medium text-slate-600"
                >
                  {label}
                  {required && <span className="text-red-500"> *</span>}
                </label>
                <input
                  id={`ph-${key}`}
                  type="text"
                  value={form[key] as string}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
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
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? <span className="spinner" /> : null}
              {submitting ? "Saving…" : editing ? "Save changes" : "Create pharmacy"}
            </button>
            <button type="button" onClick={closeForm} className="btn btn-outline">
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="card mb-5 flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="relative min-w-[220px] flex-1">
          <SearchIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by name or city..."
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
        </div>
        <div className="relative">
          <FilterIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <select
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value)}
            aria-label="Filter by status"
            className="rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-8 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </div>

      {error ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-slate-900" /> Loading pharmacies…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No pharmacies match your filters.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Unit ID</th>
                <th className="px-4 py-3">City</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {p.name}
                    {p.is_branch && (
                      <span className="ml-2 chip bg-slate-100 text-slate-600">Branch</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-600">{p.pharmapi_unit_id}</td>
                  <td className="px-4 py-3 text-slate-700">{p.city ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{p.phone ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`chip ${
                        p.active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {p.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => openEdit(p)} className="btn btn-outline">
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onToggle(p)}
                        disabled={togglingId === p.id}
                        className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {togglingId === p.id ? <span className="spinner" /> : null}
                        {p.active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
