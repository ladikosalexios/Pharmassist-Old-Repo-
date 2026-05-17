import { useEffect, useState } from "react";
import { SearchIcon, FilterIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import {
  activatePharmacist,
  deactivatePharmacist,
  listPharmacists,
  type Pharmacist,
} from "../../lib/adminApi";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function AdminPharmacists() {
  const { toast } = useToast();
  const [items, setItems] = useState<Pharmacist[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  function reload() {
    setLoading(true);
    setError(null);
    listPharmacists({
      q: query || undefined,
      active: activeFilter === "" ? undefined : activeFilter === "true",
      limit: 200,
    })
      .then((res) => setItems(res.items))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load pharmacists."),
      )
      .finally(() => setLoading(false));
  }

  useEffect(reload, [query, activeFilter]);

  async function onToggle(p: Pharmacist) {
    setTogglingId(p.id);
    try {
      if (p.active) {
        await deactivatePharmacist(p.id);
      } else {
        await activatePharmacist(p.id);
      }
      toast(p.active ? "Pharmacist deactivated" : "Pharmacist activated", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not update the pharmacist.", "error");
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pharmacists</h1>
          <p className="mt-1 text-sm text-slate-500">
            Pharmacists onboard themselves through invitations. Deactivating locks a pharmacist out
            immediately.
          </p>
        </div>
      </div>

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
            placeholder="Search by name or email..."
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
          <span className="spinner text-slate-900" /> Loading pharmacists…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No pharmacists match your filters.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Licence</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Last login</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-900">{p.full_name}</td>
                  <td className="px-4 py-3 text-slate-700">{p.email}</td>
                  <td className="px-4 py-3 font-mono text-slate-600">{p.eof_licence_no}</td>
                  <td className="px-4 py-3 text-slate-600">{p.phone ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDate(p.last_login_at)}</td>
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
