import { useState, type FormEvent } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { ShieldIcon, EyeIcon, EyeOffIcon, AlertCircleIcon } from "../components/Icons";

export function Login() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/dashboard" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setErr(null);
    if (!email.trim() || !password) {
      setErr("Please enter your email and password.");
      return;
    }
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      navigate("/dashboard", { replace: true });
    } catch (e) {
      if (e instanceof ApiError) {
        setErr(e.message || "Sign in failed. Please check your credentials.");
      } else {
        setErr("Cannot reach the server. Make sure the API is running.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-[420px] rounded-2xl border border-slate-200 bg-white p-8 shadow-cardLg sm:p-10">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-white">
          <ShieldIcon width={30} height={30} />
        </div>
        <h1 className="text-center text-2xl font-bold text-brand-600">PharmAssist</h1>
        <p className="mt-1.5 text-center text-[13px] leading-relaxed text-slate-500">
          Decision Support System · E.O.Φ. Compliant · Pharmacist Portal
        </p>

        <form onSubmit={onSubmit} noValidate className="mt-7">
          {err && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{err}</span>
            </div>
          )}

          <label htmlFor="email" className="mb-1.5 block text-[13px] font-medium text-slate-600">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="pharmacist@demo.gr"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          />

          <div className="mt-3.5 flex items-center justify-between">
            <label htmlFor="password" className="text-[13px] font-medium text-slate-600">
              Password
            </label>
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setErr(
                  "Password recovery is not yet available. Please contact your pharmacy admin.",
                );
              }}
              className="text-[13px] font-medium text-brand-600 hover:underline"
            >
              Forgot password?
            </a>
          </div>
          <div className="relative mt-1.5">
            <input
              id="password"
              type={showPw ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 pr-11 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
            />
            <button
              type="button"
              aria-label={showPw ? "Hide password" : "Show password"}
              onClick={() => setShowPw((s) => !s)}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              {showPw ? <EyeOffIcon width={18} height={18} /> : <EyeIcon width={18} height={18} />}
            </button>
          </div>

          <button type="submit" disabled={submitting} className="btn btn-primary mt-5 w-full py-3">
            {submitting ? (
              <>
                <span className="spinner" /> Signing in…
              </>
            ) : (
              "Sign In"
            )}
          </button>

          <div className="mt-4 text-center text-[13px] text-slate-500">
            New to PharmAssist?{" "}
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setErr("Pharmacy registration is not yet available in this demo build.");
              }}
              className="font-medium text-brand-600 hover:underline"
            >
              First time? Register your pharmacy licence
            </a>
          </div>
        </form>

        <div className="mt-7 border-t border-slate-200 pt-5 text-center text-[11px] leading-relaxed text-slate-500">
          Access restricted to licensed pharmacists. Regulated under Εθνικός Οργανισμός Φαρμάκων
          (Ε.Ο.Φ.)
        </div>
      </div>
    </div>
  );
}
