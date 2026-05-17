import { useEffect, useState } from "react";
import {
  SearchIcon,
  FilterIcon,
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "../../components/Icons";
import { ApiError } from "../../lib/api";
import { listAuditLogs, type AuditLogEntry } from "../../lib/adminApi";

const LIMIT = 50;

const ACTOR_TONE: Record<AuditLogEntry["actor_type"], string> = {
  staff: "bg-slate-900 text-white",
  pharmacist: "bg-blue-100 text-blue-800",
  system: "bg-slate-100 text-slate-600",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function AdminAuditLog() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionInput, setActionInput] = useState("");
  const [action, setAction] = useState("");
  const [resourceInput, setResourceInput] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setAction(actionInput.trim()), 250);
    return () => clearTimeout(t);
  }, [actionInput]);

  useEffect(() => {
    const t = setTimeout(() => setResourceType(resourceInput.trim()), 250);
    return () => clearTimeout(t);
  }, [resourceInput]);

  useEffect(() => {
    setOffset(0);
  }, [action, resourceType, dateFrom, dateTo]);

  useEffect(() => {
    // Changing a filter resets `offset`, so this effect can fire twice in
    // quick succession — guard against the earlier response landing last.
    let active = true;
    setLoading(true);
    setError(null);
    listAuditLogs({
      action: action || undefined,
      resource_type: resourceType || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: LIMIT,
      offset,
    })
      .then((res) => {
        if (!active) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e: unknown) => {
        if (active) {
          setError(e instanceof ApiError ? e.message : "Could not load audit logs.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [action, resourceType, dateFrom, dateTo, offset]);

  return (
    <div className="p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-bold text-slate-900">Audit Log</h1>
        <p className="mt-1 text-sm text-slate-500">
          Read-only record of every change made through the admin console.
        </p>
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
            value={actionInput}
            onChange={(e) => setActionInput(e.target.value)}
            placeholder="Filter by action, e.g. pharmacy.create"
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
        </div>
        <div className="relative min-w-[180px]">
          <FilterIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            type="search"
            value={resourceInput}
            onChange={(e) => setResourceInput(e.target.value)}
            placeholder="Resource type"
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          From
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            aria-label="Filter from date"
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-700 outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          To
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            aria-label="Filter to date"
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-700 outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
        </label>
      </div>

      {error ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-slate-900" /> Loading audit logs…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No audit log entries match your filters.
        </div>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Resource</th>
                  <th className="px-4 py-3">Actor</th>
                  <th className="px-4 py-3">Pharmacy</th>
                  <th className="px-4 py-3">IP</th>
                </tr>
              </thead>
              <tbody>
                {items.map((entry) => (
                  <tr key={entry.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 text-slate-600">{formatDate(entry.occurred_at)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{entry.action}</td>
                    <td className="px-4 py-3 text-slate-700">
                      {entry.resource_type ?? "—"}
                      {entry.resource_id && (
                        <div className="text-xs text-slate-500">{entry.resource_id}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      <div className="flex items-center gap-2">
                        <span>{entry.actor_name ?? "—"}</span>
                        <span className={`chip ${ACTOR_TONE[entry.actor_type]}`}>
                          {entry.actor_type}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{entry.pharmacy_name ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">
                      {entry.ip_address ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-slate-500">
              Showing {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
                disabled={offset === 0}
                className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ChevronLeftIcon /> Prev
              </button>
              <button
                type="button"
                onClick={() => setOffset((o) => o + LIMIT)}
                disabled={offset + LIMIT >= total}
                className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
              >
                Next <ChevronRightIcon />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
