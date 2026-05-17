import { useEffect, useState, type FormEvent } from "react";
import { SettingsIcon, SearchIcon, FilterIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import {
  activateStaff,
  createStaff,
  deactivateStaff,
  listStaff,
  type Staff,
  type StaffCreate,
} from "../../lib/adminApi";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function AdminStaff() {
  const { toast } = useToast();
  const [items, setItems] = useState<Staff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
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
    listStaff({
      q: query || undefined,
      active: activeFilter === "" ? undefined : activeFilter === "true",
      limit: 200,
    })
      .then((res) => setItems(res.items))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load staff."))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [query, activeFilter]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setFormErr(null);
    if (!email.trim() || !fullName.trim() || !password) {
      setFormErr("Email, full name and password are all required.");
      return;
    }
    if (password.length < 8) {
      setFormErr("Password must be at least 8 characters.");
      return;
    }
    const payload: StaffCreate = {
      email: email.trim(),
      full_name: fullName.trim(),
      password,
    };
    setSubmitting(true);
    try {
      await createStaff(payload);
      toast("Staff account created", "success");
      setEmail("");
      setFullName("");
      setPassword("");
      setShowForm(false);
      reload();
    } catch (e) {
      setFormErr(e instanceof ApiError ? e.message : "Could not create the staff account.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onToggle(s: Staff) {
    setTogglingId(s.id);
    try {
      if (s.active) {
        await deactivateStaff(s.id);
      } else {
        await activateStaff(s.id);
      }
      toast(s.active ? "Staff account deactivated" : "Staff account activated", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not update the staff account.", "error");
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Staff</h1>
          <p className="mt-1 text-sm text-slate-500">
            PharmAssist company staff accounts — these users manage the admin console.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setShowForm((s) => !s);
            setFormErr(null);
          }}
          className="btn bg-slate-900 text-white hover:bg-slate-800"
        >
          <SettingsIcon /> New Staff
        </button>
      </div>

      {showForm && (
        <form onSubmit={onCreate} className="card mb-5 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Create staff account</h2>
          {formErr && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{formErr}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="staff-email"
                className="mb-1.5 block text-[13px] font-medium text-slate-600"
              >
                Email
                <span className="text-red-500"> *</span>
              </label>
              <input
                id="staff-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
              />
            </div>
            <div>
              <label
                htmlFor="staff-full-name"
                className="mb-1.5 block text-[13px] font-medium text-slate-600"
              >
                Full name
                <span className="text-red-500"> *</span>
              </label>
              <input
                id="staff-full-name"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
              />
            </div>
            <div>
              <label
                htmlFor="staff-password"
                className="mb-1.5 block text-[13px] font-medium text-slate-600"
              >
                Password
                <span className="text-red-500"> *</span>
              </label>
              <input
                id="staff-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
              />
              <p className="mt-1.5 text-xs text-slate-500">Minimum 8 characters.</p>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? <span className="spinner" /> : null}
              {submitting ? "Creating…" : "Create staff account"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="btn btn-outline">
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
          <span className="spinner text-slate-900" /> Loading staff…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No staff match your filters.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Last login</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-900">{s.full_name}</td>
                  <td className="px-4 py-3 text-slate-700">{s.email}</td>
                  <td className="px-4 py-3 text-slate-600">{s.role}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDate(s.last_login_at)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`chip ${
                        s.active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {s.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => onToggle(s)}
                        disabled={togglingId === s.id}
                        className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {togglingId === s.id ? <span className="spinner" /> : null}
                        {s.active ? "Deactivate" : "Activate"}
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
