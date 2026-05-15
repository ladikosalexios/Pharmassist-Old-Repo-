import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login as apiLogin, logout as apiLogout, me as apiMe } from "./api";

interface AuthUser {
  name: string;
  pharmacy: string;
  email?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  // The httpOnly `pharmassist_session` cookie is the source of truth — we
  // can't read it from JS, so always probe /auth/me on mount and let the
  // backend tell us whether we're authenticated.
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    apiMe()
      .then((data) => setUser({ name: data.name, pharmacy: data.pharmacy, email: data.email }))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      async signIn(email, password) {
        const data = await apiLogin(email, password);
        // The backend's LoginResponse doesn't carry `email`, so reuse the
        // value the form submitted — keeps `user.email` populated immediately
        // instead of waiting for a page reload to hydrate it from /auth/me.
        setUser({ name: data.pharmacist_name, pharmacy: data.pharmacy, email });
      },
      async signOut() {
        // Swallow upstream failures — we still want to clear local state
        // (e.g. server-side cookie was already gone, or network blip).
        try {
          await apiLogout();
        } catch {
          /* intentional */
        }
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
