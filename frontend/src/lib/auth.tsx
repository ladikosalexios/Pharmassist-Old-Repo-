import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login as apiLogin, me as apiMe } from "./api";

interface AuthUser {
  name: string;
  pharmacy: string;
  email?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const name = localStorage.getItem("pa_name");
    const pharmacy = localStorage.getItem("pa_pharmacy");
    const token = localStorage.getItem("pa_token");
    return token && name ? { name, pharmacy: pharmacy ?? "" } : null;
  });
  const [loading, setLoading] = useState<boolean>(!!localStorage.getItem("pa_token"));

  useEffect(() => {
    const token = localStorage.getItem("pa_token");
    if (!token) {
      setLoading(false);
      return;
    }
    apiMe()
      .then((data) => {
        setUser({ name: data.name, pharmacy: data.pharmacy, email: data.email });
        localStorage.setItem("pa_name", data.name);
        localStorage.setItem("pa_pharmacy", data.pharmacy);
      })
      .catch(() => {
        localStorage.removeItem("pa_token");
        localStorage.removeItem("pa_name");
        localStorage.removeItem("pa_pharmacy");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      async signIn(email, password) {
        const data = await apiLogin(email, password);
        localStorage.setItem("pa_token", data.access_token);
        localStorage.setItem("pa_name", data.pharmacist_name);
        localStorage.setItem("pa_pharmacy", data.pharmacy);
        setUser({ name: data.pharmacist_name, pharmacy: data.pharmacy });
      },
      signOut() {
        localStorage.removeItem("pa_token");
        localStorage.removeItem("pa_name");
        localStorage.removeItem("pa_pharmacy");
        setUser(null);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
