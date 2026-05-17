import { useEffect, useState, type FormEvent } from "react";
import { MailIcon, SearchIcon, FilterIcon, AlertCircleIcon, XIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import {
  createInvitation,
  listInvitations,
  listPharmacies,
  revokeInvitation,
  type Invitation,
  type Pharmacy,
} from "../../lib/adminApi";

const STATUS_TONE: Record<Invitation["status"], string> = {
  pending: "bg-amber-100 text-amber-800",
  accepted: "bg-emerald-100 text-emerald-800",
  expired: "bg-slate-100 text-slate-600",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function AdminInvitations() {
  const { toast } = useToast();
  const [items, setItems] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");

  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [pharmacyId, setPharmacyId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  function reload() {
    setLoading(true);
    setError(null);
    listInvitations({ q: query || undefined, status: status || undefined, limit: 200 })
      .then((res) => setItems(res.items))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load invitations."),
      )
      .finally(() => setLoading(false));
  }

  useEffect(reload, [query, status]);

  useEffect(() => {
    listPharmacies({ active: true, limit: 200 })
      .then((res) => setPharmacies(res.items))
      .catch(() => setPharmacies([]));
  }, []);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setFormErr(null);
    if (!email.trim() || !pharmacyId) {
      setFormErr("Email and pharmacy are both required.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await createInvitation(email.trim(), pharmacyId);
      setLastUrl(`${window.location.origin}${res.invite_url}`);
      setEmail("");
      setPharmacyId("");
      setShowForm(false);
      toast("Invitation created", "success");
      reload();
    } catch (e) {
      setFormErr(e instanceof ApiError ? e.message : "Could not create the invitation.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onRevoke(id: string) {
    setRevokingId(id);
    try {
      await revokeInvitation(id);
      toast("Invitation revoked", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not revoke the invitation.", "error");
    } finally {
      setRevokingId(null);
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
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Invitations</h1>
          <p className="mt-1 text-sm text-slate-500">
            Onboarding invites for pharmacists. There is no email delivery yet — copy the link and
            send it manually.
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
          <MailIcon /> New Invitation
        </button>
      </div>

      {lastUrl && (
        <div className="card mb-5 flex flex-wrap items-center gap-3 border-emerald-200 bg-emerald-50 px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
              Invite link — send this to the pharmacist
            </div>
            <div className="mt-0.5 break-all font-mono text-[13px] text-emerald-900">{lastUrl}</div>
          </div>
          <button type="button" onClick={() => copyUrl(lastUrl)} className="btn btn-outline">
            Copy link
          </button>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setLastUrl(null)}
            className="rounded-md p-1.5 text-emerald-700 hover:bg-emerald-100"
          >
            <XIcon width={16} height={16} />
          </button>
        </div>
      )}

      {showForm && (
        <form onSubmit={onCreate} className="card mb-5 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Create invitation</h2>
          {formErr && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{formErr}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="inv-email"
                className="mb-1.5 block text-[13px] font-medium text-slate-600"
              >
                Pharmacist email
              </label>
              <input
                id="inv-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="pharmacist@example.gr"
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
              />
            </div>
            <div>
              <label
                htmlFor="inv-pharmacy"
                className="mb-1.5 block text-[13px] font-medium text-slate-600"
              >
                Pharmacy
              </label>
              <select
                id="inv-pharmacy"
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
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? <span className="spinner" /> : null}
              {submitting ? "Creating…" : "Create invitation"}
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
            placeholder="Search by email..."
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
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Filter by status"
            className="rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-8 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="expired">Expired</option>
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
          <span className="spinner text-slate-900" /> Loading invitations…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No invitations match your filters.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Pharmacy</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Invited by</th>
                <th className="px-4 py-3">Expires</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((inv) => (
                <tr key={inv.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-900">{inv.email}</td>
                  <td className="px-4 py-3 text-slate-700">{inv.pharmacy_name}</td>
                  <td className="px-4 py-3">
                    <span className={`chip capitalize ${STATUS_TONE[inv.status]}`}>
                      {inv.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{inv.invited_by_name ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDate(inv.expires_at)}</td>
                  <td className="px-4 py-3 text-right">
                    {inv.status === "pending" && (
                      <button
                        type="button"
                        onClick={() => onRevoke(inv.id)}
                        disabled={revokingId === inv.id}
                        className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {revokingId === inv.id ? <span className="spinner" /> : null}
                        Revoke
                      </button>
                    )}
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
