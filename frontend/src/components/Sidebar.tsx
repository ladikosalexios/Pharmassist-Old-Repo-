import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import {
  PillIcon,
  GridIcon,
  UsersIcon,
  ClipboardIcon,
  AlertTriangleIcon,
  SettingsIcon,
  LogOutIcon,
} from "./Icons";

const NAV = [
  { to: "/dashboard", labelKey: "nav.counter", Icon: GridIcon },
  { to: "/patients", labelKey: "nav.patients", Icon: UsersIcon },
  { to: "/history", labelKey: "nav.history", Icon: ClipboardIcon },
  { to: "/side-effects", labelKey: "nav.reports", Icon: AlertTriangleIcon },
  { to: "/settings", labelKey: "nav.settings", Icon: SettingsIcon },
];

export function Sidebar() {
  const { user, signOut } = useAuth();
  const { t } = useTranslation();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2.5 border-b border-slate-200 px-5 py-[18px]">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
          <PillIcon width={18} height={18} />
        </div>
        <div className="text-[15px] font-bold tracking-tight text-brand-600">
          {t("common.appName")}
        </div>
      </div>

      <nav className="flex-1 p-3">
        {NAV.map(({ to, labelKey, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `mb-1 flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors ${
                isActive
                  ? "bg-brand-100 text-brand-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Icon width={17} height={17} />
            {t(labelKey)}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-slate-200 p-3">
        <div className="mb-2 px-3">
          <div className="truncate text-[13px] font-semibold text-slate-900">
            {user?.name ?? "—"}
          </div>
          <div className="truncate text-[12px] text-slate-500">{user?.pharmacy ?? "—"}</div>
        </div>
        <button
          type="button"
          onClick={signOut}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-900"
        >
          <LogOutIcon width={16} height={16} /> {t("nav.signOut")}
        </button>
      </div>
    </aside>
  );
}
