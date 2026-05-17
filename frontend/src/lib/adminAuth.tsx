import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  adminLogin as apiAdminLogin,
  adminLogout as apiAdminLogout,
  adminMe as apiAdminMe,
  type AdminUser,
} from "./adminApi";

interface AdminAuthContextValue {
  admin: AdminUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AdminAuthContext = createContext<AdminAuthContextValue | undefined>(undefined);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  // The httpOnly `pharmassist_admin_session` cookie is the source of truth —
  // JS can't read it, so always probe /admin/me on mount and let the backend
  // tell us whether a staff session is live. Separate from the pharmacist
  // AuthProvider — the two cookies and tokens never cross over.
  const [admin, setAdmin] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    apiAdminMe()
      .then((data) => setAdmin(data))
      .catch(() => setAdmin(null))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AdminAuthContextValue>(
    () => ({
      admin,
      loading,
      async signIn(email, password) {
        setAdmin(await apiAdminLogin(email, password));
      },
      async signOut() {
        // Swallow upstream failures — we still want to clear local state
        // (server cookie may already be gone, or a network blip).
        try {
          await apiAdminLogout();
        } catch {
          /* intentional */
        }
        setAdmin(null);
      },
    }),
    [admin, loading],
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used within AdminAuthProvider");
  return ctx;
}
