import { Outlet, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sidebar } from "./Sidebar";
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
        toast("Opening next prescription…", "info");
        try {
          const next = await getNextPrescription();
          navigate(`/prescription/${next.rxId}`);
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) {
            toast("No pending prescriptions in the queue.", "info");
          } else {
            toast(
              e instanceof ApiError ? e.message : "Could not load the next prescription.",
              "error",
            );
          }
        }
      },
    },
    { enabled: !!user },
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        <span className="spinner mr-2 text-brand-600" /> {t("shell.loading")}
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-slate-50">
        <Outlet />
      </main>
    </div>
  );
}
