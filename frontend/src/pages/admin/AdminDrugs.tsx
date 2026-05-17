import { useEffect, useState, type FormEvent } from "react";
import { PillIcon, SearchIcon, FilterIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import { createDrug, listDrugs, updateDrug, type Drug, type DrugCreate } from "../../lib/adminApi";

interface FormState {
  gns_code: string;
  atc_code: string;
  atc_class: string;
  name_gr: string;
  name_en: string;
  interaction_group: string;
}

const EMPTY: FormState = {
  gns_code: "",
  atc_code: "",
  atc_class: "",
  name_gr: "",
  name_en: "",
  interaction_group: "",
};

const TEXT_FIELDS: { key: keyof FormState; label: string; required?: boolean }[] = [
  { key: "gns_code", label: "GNS code", required: true },
  { key: "atc_code", label: "ATC code", required: true },
  { key: "atc_class", label: "ATC class", required: true },
  { key: "name_gr", label: "Name (Greek)", required: true },
  { key: "name_en", label: "Name (English)" },
  { key: "interaction_group", label: "Interaction group" },
];

function toForm(d: Drug): FormState {
  return {
    gns_code: d.gns_code,
    atc_code: d.atc_code,
    atc_class: d.atc_class,
    name_gr: d.name_gr,
    name_en: d.name_en ?? "",
    interaction_group: d.interaction_group ?? "",
  };
}

export function AdminDrugs() {
  const { toast } = useToast();
  const [items, setItems] = useState<Drug[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Drug | null>(null);
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
    listDrugs({
      q: query || undefined,
      active: activeFilter === "" ? undefined : activeFilter === "true",
      limit: 200,
    })
      .then((res) => setItems(res.items))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load drugs."))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [query, activeFilter]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormErr(null);
    setShowForm(true);
  }

  function openEdit(d: Drug) {
    setEditing(d);
    setForm(toForm(d));
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
    if (
      !form.gns_code.trim() ||
      !form.atc_code.trim() ||
      !form.atc_class.trim() ||
      !form.name_gr.trim()
    ) {
      setFormErr("GNS code, ATC code, ATC class and Greek name are all required.");
      return;
    }
    const payload: DrugCreate = {
      gns_code: form.gns_code.trim(),
      atc_code: form.atc_code.trim(),
      atc_class: form.atc_class.trim(),
      name_gr: form.name_gr.trim(),
      name_en: form.name_en.trim() || null,
      interaction_group: form.interaction_group.trim() || null,
    };
    setSubmitting(true);
    try {
      if (editing) {
        await updateDrug(editing.id, payload);
        toast("Drug updated", "success");
      } else {
        await createDrug(payload);
        toast("Drug created", "success");
      }
      closeForm();
      reload();
    } catch (e) {
      setFormErr(e instanceof ApiError ? e.message : "Could not save the drug.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onToggle(d: Drug) {
    setTogglingId(d.id);
    try {
      await updateDrug(d.id, { active: !d.active });
      toast(d.active ? "Drug deactivated" : "Drug activated", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not update the drug.", "error");
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Drug Catalog</h1>
          <p className="mt-1 text-sm text-slate-500">
            Clinically-curated drug reference data that feeds the prescription safety engine.
          </p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="btn bg-slate-900 text-white hover:bg-slate-800"
        >
          <PillIcon /> New Drug
        </button>
      </div>

      {showForm && (
        <form onSubmit={onSubmit} className="card mb-5 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">
            {editing ? `Edit ${editing.name_gr}` : "Create drug"}
          </h2>
          {formErr && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{formErr}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {TEXT_FIELDS.map(({ key, label, required }) => (
              <div key={key}>
                <label
                  htmlFor={`drug-${key}`}
                  className="mb-1.5 block text-[13px] font-medium text-slate-600"
                >
                  {label}
                  {required && <span className="text-red-500"> *</span>}
                </label>
                <input
                  id={`drug-${key}`}
                  type="text"
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
                />
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? <span className="spinner" /> : null}
              {submitting ? "Saving…" : editing ? "Save changes" : "Create drug"}
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
            placeholder="Search by name or GNS code..."
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
          <span className="spinner text-slate-900" /> Loading drugs…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No drugs match your filters.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">GNS code</th>
                <th className="px-4 py-3">ATC code</th>
                <th className="px-4 py-3">ATC class</th>
                <th className="px-4 py-3">Interaction group</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{d.name_gr}</div>
                    {d.name_en && <div className="text-xs text-slate-500">{d.name_en}</div>}
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-600">{d.gns_code}</td>
                  <td className="px-4 py-3 font-mono text-slate-600">{d.atc_code}</td>
                  <td className="px-4 py-3 text-slate-700">{d.atc_class}</td>
                  <td className="px-4 py-3 text-slate-600">{d.interaction_group ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`chip ${
                        d.active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {d.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => openEdit(d)} className="btn btn-outline">
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onToggle(d)}
                        disabled={togglingId === d.id}
                        className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {togglingId === d.id ? <span className="spinner" /> : null}
                        {d.active ? "Deactivate" : "Activate"}
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
