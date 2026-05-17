import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GridIcon, SearchIcon, AlertCircleIcon } from "../../components/Icons";
import { ApiError } from "../../lib/api";
import { listPharmacies, type PharmacyListItem } from "../../lib/adminApi";

export function AdminPharmacies() {
  const navigate = useNavigate();
  const [items, setItems] = useState<PharmacyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listPharmacies({ q: query || undefined, limit: 200 })
      .then((res) => {
        if (active) setItems(res.items);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof ApiError ? e.message : "Could not load pharmacies.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query]);

  return (
    <div className="p-8">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pharmacies</h1>
          <p className="mt-1 text-sm text-slate-500">
            Every pharmacy on the platform. Open one to see its pharmacists, invitations, and
            activity.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate("/admin/onboard")}
          className="btn bg-slate-900 text-white hover:bg-slate-800"
        >
          <GridIcon /> Onboard pharmacy
        </button>
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
            placeholder="Search by name or city..."
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
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
          No pharmacies match your search.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">City</th>
                <th className="px-4 py-3">Pharmacists</th>
                <th className="px-4 py-3">Pending invites</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/admin/pharmacies/${p.id}`)}
                  className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-medium text-slate-900">{p.name}</td>
                  <td className="px-4 py-3 text-slate-700">{p.city ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{p.pharmacist_count}</td>
                  <td className="px-4 py-3 text-slate-600">{p.pending_invite_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
