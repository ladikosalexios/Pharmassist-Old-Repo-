import { NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { GridIcon, FileTextIcon, UsersIcon, ClockIcon, AlertTriangleIcon, SettingsIcon, LogOutIcon, ShieldIcon } from "./Icons";

const NAV = [
  { to: "/dashboard",     label: "Dashboard",        Icon: GridIcon },
  { to: "/prescriptions", label: "Prescriptions",    Icon: FileTextIcon },
  { to: "/patients",      label: "Patients",         Icon: UsersIcon },
  { to: "/history",       label: "History",          Icon: ClockIcon },
  { to: "/adr",           label: "Side Effect Reports", Icon: AlertTriangleIcon },
  { to: "/settings",      label: "Settings",         Icon: SettingsIcon },
];

export function Sidebar() {
  const { user, signOut } = useAuth();
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
          <ShieldIcon width={18} height={18} />
        </div>
        <div className="text-base font-bold text-brand-600">PharmAssist</div>
      </div>

      <nav className="flex-1 p-3">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `mb-1 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive ? "bg-brand-100 text-brand-600" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
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
          <div className="text-sm font-semibold text-slate-900">{user?.name ?? "—"}</div>
          <div className="text-xs text-slate-500">{user?.pharmacy ?? "—"}</div>
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
