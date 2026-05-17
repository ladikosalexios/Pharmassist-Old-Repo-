import { useEffect, useState, type ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { ChevronLeftIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import { getPharmacy, type Invitation, type PharmacyDetail } from "../../lib/adminApi";

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

export function AdminPharmacyDetail() {
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const [data, setData] = useState<PharmacyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let active = true;
    setLoading(true);
    setError(null);
    getPharmacy(id)
      .then((res) => {
        if (active) setData(res);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof ApiError ? e.message : "Could not load the pharmacy.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  async function copyInvite(url: string) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${url}`);
      toast("Invite link copied", "success");
    } catch {
      toast("Could not copy the link.", "error");
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

      {error ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : loading || !data ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-slate-900" /> Loading…
        </div>
      ) : (
        <>
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-slate-900">{data.pharmacy.name}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {[data.pharmacy.address, data.pharmacy.city].filter(Boolean).join(", ") ||
                "No address on file"}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="chip bg-slate-100 text-slate-600">
                Unit ID {data.pharmacy.pharmapi_unit_id}
              </span>
              <span
                className={`chip ${
                  data.pharmacy.active
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {data.pharmacy.active ? "Active" : "Inactive"}
              </span>
              {data.pharmacy.is_branch && (
                <span className="chip bg-slate-100 text-slate-600">Branch</span>
              )}
            </div>
          </div>

          <Section title="Pharmacists" count={data.pharmacists.length}>
            {data.pharmacists.length === 0 ? (
              <Empty>No pharmacists yet — they appear here once an invite is accepted.</Empty>
            ) : (
              <Table head={["Name", "Email", "Licence", "Status"]}>
                {data.pharmacists.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-900">{p.full_name}</td>
                    <td className="px-4 py-3 text-slate-700">{p.email}</td>
                    <td className="px-4 py-3 font-mono text-slate-600">{p.eof_licence_no}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`chip ${
                          p.active
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {p.active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </Section>

          <Section title="Invitations" count={data.invitations.length}>
            {data.invitations.length === 0 ? (
              <Empty>No invitations.</Empty>
            ) : (
              <Table head={["Email", "Status", "Expires", "Sent", "Link"]}>
                {data.invitations.map((inv) => (
                  <tr key={inv.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-900">{inv.email}</td>
                    <td className="px-4 py-3">
                      <span className={`chip capitalize ${STATUS_TONE[inv.status]}`}>
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(inv.expires_at)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(inv.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      {inv.status === "pending" && (
                        <button
                          type="button"
                          onClick={() => copyInvite(inv.invite_url)}
                          className="btn btn-outline"
                        >
                          Copy link
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </Section>

          <Section title="Activity" count={data.audit.length}>
            {data.audit.length === 0 ? (
              <Empty>No activity recorded.</Empty>
            ) : (
              <Table head={["Time", "Action", "Resource", "By"]}>
                {data.audit.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 text-slate-600">{formatDate(row.occurred_at)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{row.action}</td>
                    <td className="px-4 py-3 text-slate-600">{row.resource_type ?? "—"}</td>
                    <td className="px-4 py-3 text-slate-700">{row.actor_name ?? row.actor_type}</td>
                  </tr>
                ))}
              </Table>
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="mb-6">
      <h2 className="mb-2 text-sm font-semibold text-slate-900">
        {title} <span className="text-slate-400">({count})</span>
      </h2>
      {children}
    </section>
  );
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            {head.map((h) => (
              <th key={h} className="px-4 py-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="card px-4 py-6 text-center text-sm text-slate-500">{children}</div>;
}
