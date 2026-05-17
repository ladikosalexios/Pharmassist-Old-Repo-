import { NavLink } from "react-router-dom";
import { useAdminAuth } from "../lib/adminAuth";
import {
  ShieldIcon,
  MailIcon,
  GridIcon,
  UsersIcon,
  SettingsIcon,
  PillIcon,
  AlertTriangleIcon,
  FileTextIcon,
  ClipboardIcon,
  LogOutIcon,
} from "./Icons";

const NAV = [
  { to: "/admin/invitations", label: "Invitations", Icon: MailIcon },
  { to: "/admin/pharmacies", label: "Pharmacies", Icon: GridIcon },
  { to: "/admin/pharmacists", label: "Pharmacists", Icon: UsersIcon },
  { to: "/admin/staff", label: "Staff", Icon: SettingsIcon },
  { to: "/admin/drugs", label: "Drug Catalog", Icon: PillIcon },
  { to: "/admin/safety-rules", label: "Safety Rules", Icon: AlertTriangleIcon },
  { to: "/admin/demo", label: "Demo Data", Icon: FileTextIcon },
  { to: "/admin/audit-logs", label: "Audit Log", Icon: ClipboardIcon },
];

export function AdminSidebar() {
  const { admin, signOut } = useAdminAuth();
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white">
          <ShieldIcon width={18} height={18} />
        </div>
        <div>
          <div className="text-base font-bold text-slate-900">PharmAssist</div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Admin Console
          </div>
        </div>
      </div>

      <nav className="flex-1 p-3">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `mb-1 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Icon width={17} height={17} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-slate-200 p-3">
        <div className="mb-2 px-3">
          <div className="text-sm font-semibold text-slate-900">{admin?.name ?? "—"}</div>
          <div className="text-xs text-slate-500">{admin?.email ?? "—"}</div>
        </div>
        <button
          type="button"
          onClick={signOut}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-500 hover:bg-slate-50 hover:text-slate-900"
        >
          <LogOutIcon /> Sign out
        </button>
      </div>
    </aside>
  );
}
