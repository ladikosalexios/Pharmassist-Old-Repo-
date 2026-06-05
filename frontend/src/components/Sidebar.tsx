import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";
import {
  PillIcon,
  GridIcon,
  UsersIcon,
  ClipboardIcon,
  AlertTriangleIcon,
  SettingsIcon,
  LogOutIcon,
  MenuIcon,
  XIcon,
  SunIcon,
  MoonIcon,
} from "./Icons";

const NAV = [
  { to: "/dashboard", labelKey: "nav.counter", Icon: GridIcon },
  { to: "/patients", labelKey: "nav.patients", Icon: UsersIcon },
  { to: "/history", labelKey: "nav.history", Icon: ClipboardIcon },
  { to: "/side-effects", labelKey: "nav.reports", Icon: AlertTriangleIcon },
  { to: "/settings", labelKey: "nav.settings", Icon: SettingsIcon },
];

/** Two-letter initials for the mobile avatar chip. */
function initialsOf(name: string | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/** Shared nav links. `padY` lets the drawer use taller (≥40px) touch targets. */
function NavItems({ onNavigate, padY = "py-2" }: { onNavigate?: () => void; padY?: string }) {
  const { t } = useTranslation();
  return (
    <>
      {NAV.map(({ to, labelKey, Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            `mb-1 flex items-center gap-2.5 rounded-lg px-3 ${padY} text-[13.5px] font-medium transition-colors ${
              isActive
                ? "bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            }`
          }
        >
          <Icon width={17} height={17} />
          {t(labelKey)}
        </NavLink>
      ))}
    </>
  );
}

/** User block + theme toggle + sign out — shared by the desktop rail and the drawer. */
function SidebarFooter({ onNavigate, padY = "py-2" }: { onNavigate?: () => void; padY?: string }) {
  const { user, signOut } = useAuth();
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const rowClass = `flex w-full items-center gap-2.5 rounded-lg px-3 ${padY} text-[13px] text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100`;

  return (
    <>
      <div className="mb-2 px-3">
        <div className="truncate text-[13px] font-semibold text-slate-900 dark:text-slate-100">
          {user?.name ?? "—"}
        </div>
        <div className="truncate text-[12px] text-slate-500 dark:text-slate-400">
          {user?.pharmacy ?? "—"}
        </div>
      </div>
      <button type="button" onClick={toggleTheme} aria-pressed={isDark} className={rowClass}>
        {isDark ? <SunIcon width={16} height={16} /> : <MoonIcon width={16} height={16} />}
        {isDark ? t("nav.lightMode") : t("nav.darkMode")}
      </button>
      <button
        type="button"
        onClick={() => {
          onNavigate?.();
          signOut();
        }}
        className={rowClass}
      >
        <LogOutIcon width={16} height={16} /> {t("nav.signOut")}
      </button>
    </>
  );
}

/** Desktop rail — hidden below md, where the top bar + drawer take over. */
export function Sidebar() {
  const { t } = useTranslation();
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 md:flex">
      <div className="flex items-center gap-2.5 border-b border-slate-200 px-5 py-[18px] dark:border-slate-800">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
          <PillIcon width={18} height={18} />
        </div>
        <div className="text-[15px] font-bold tracking-tight text-brand-600 dark:text-brand-400">
          {t("common.appName")}
        </div>
      </div>

      <nav className="flex-1 p-3">
        <NavItems />
      </nav>

      <div className="border-t border-slate-200 p-3 dark:border-slate-800">
        <SidebarFooter />
      </div>
    </aside>
  );
}

/** Mobile chrome: a sticky top app bar plus a slide-in nav drawer (md:hidden). */
export function MobileNav() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);

  // Close on Escape and lock body scroll while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <>
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2.5 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95 md:hidden">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={t("nav.openMenu")}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <MenuIcon width={22} height={22} />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white">
            <PillIcon width={15} height={15} />
          </div>
          <span className="text-[15px] font-bold tracking-tight text-brand-600 dark:text-brand-400">
            {t("common.appName")}
          </span>
        </div>
        <div className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-[12px] font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
          {initialsOf(user?.name)}
        </div>
      </header>

      <div className={`fixed inset-0 z-[80] md:hidden ${open ? "" : "pointer-events-none"}`}>
        <div
          onClick={close}
          aria-hidden="true"
          className={`absolute inset-0 bg-slate-900/40 transition-opacity ${
            open ? "opacity-100" : "opacity-0"
          }`}
        />
        <aside
          role="dialog"
          aria-modal="true"
          aria-label={t("common.appName")}
          className={`absolute left-0 top-0 flex h-full w-[270px] max-w-[80%] flex-col bg-white shadow-2xl transition-transform duration-300 dark:bg-slate-900 ${
            open ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
                <PillIcon width={18} height={18} />
              </div>
              <div className="text-[15px] font-bold tracking-tight text-brand-600 dark:text-brand-400">
                {t("common.appName")}
              </div>
            </div>
            <button
              type="button"
              onClick={close}
              aria-label={t("nav.closeMenu")}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 dark:text-slate-500 dark:hover:bg-slate-800"
            >
              <XIcon width={18} height={18} />
            </button>
          </div>

          <nav className="flex-1 overflow-y-auto p-3">
            <NavItems onNavigate={close} padY="py-2.5" />
          </nav>

          <div className="border-t border-slate-200 p-3 dark:border-slate-800">
            <SidebarFooter onNavigate={close} padY="py-2.5" />
          </div>
        </aside>
      </div>
    </>
  );
}
