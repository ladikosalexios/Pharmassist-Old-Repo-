import { Outlet, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sidebar, MobileNav } from "./Sidebar";
import { useAuth } from "../lib/auth";
import { useToast } from "./Toast";
import { useKeyboardShortcuts } from "../lib/keyboard";
import { ApiError, getNextPrescription } from "../lib/api";

export function AppShell() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation();

  // Global shortcuts that should work on any authenticated page.
  useKeyboardShortcuts(
    {
      d: () => {
        toast(t("shell.openingCounter"), "info");
        navigate("/dashboard");
      },
      p: async () => {
        toast(t("shell.openingPrescription"), "info");
        try {
          const next = await getNextPrescription();
          navigate(`/prescription/${next.rxId}`);
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) {
            toast(t("shell.noPending"), "info");
          } else {
            toast(e instanceof ApiError ? e.message : t("shell.loadNextFailed"), "error");
          }
        }
      },
    },
    { enabled: !!user },
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500 dark:text-slate-400">
        <span className="spinner mr-2 text-brand-600" /> {t("shell.loading")}
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-slate-50 dark:bg-slate-950">
        <MobileNav />
        <Outlet />
      </main>
    </div>
  );
}
