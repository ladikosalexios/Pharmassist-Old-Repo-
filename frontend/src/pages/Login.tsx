import { useState, type FormEvent } from "react";
import { useNavigate, Navigate, useLocation, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { AlertCircleIcon, EyeIcon, EyeOffIcon, PillIcon } from "../components/Icons";

export function Login() {
  const { t } = useTranslation();
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const notice = (location.state as { notice?: string } | null)?.notice ?? null;

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
      setErr(t("login.missingFields"));
      return;
    }
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      navigate("/dashboard", { replace: true });
    } catch (e) {
      if (e instanceof ApiError) {
        setErr(e.message || t("login.errorHint"));
      } else {
        setErr(t("login.networkError"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-slate-50 px-4 py-16">
      <div className="w-full max-w-[420px] animate-fade-in">
        {/* brand */}
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-card">
            <PillIcon width={26} height={26} />
          </div>
          <div className="mt-3 text-2xl font-bold tracking-tight text-brand-600">
            {t("common.appName")}
          </div>
          <p className="mt-1.5 max-w-[300px] text-[13px] leading-relaxed text-slate-500">
            {t("login.tagline")}
          </p>
        </div>

        {/* card */}
        <div className="rounded-xl border border-slate-200 bg-white p-7 shadow-cardLg">
          {/* Post-redirect notice (e.g. "Account created — please log in.") */}
          {notice && (
            <div
              className="mb-5 flex items-start gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-[13px] text-emerald-800 animate-alert-in"
              role="status"
            >
              <span className="mt-0.5 shrink-0">
                <AlertCircleIcon width={16} height={16} />
              </span>
              <div>{notice}</div>
            </div>
          )}

          {err && (
            <div
              className="mb-5 flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-[13px] text-red-700 animate-alert-in"
              role="alert"
            >
              <span className="mt-0.5 shrink-0 text-red-600">
                <AlertCircleIcon width={16} height={16} />
              </span>
              <div>
                <div className="font-semibold">{t("login.errorTitle")}</div>
                <div className="text-red-600/90">{err}</div>
              </div>
            </div>
          )}

          <form onSubmit={onSubmit} noValidate className="space-y-4">
            {/* email */}
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-[13px] font-medium text-slate-700"
              >
                {t("login.emailLabel")}
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                placeholder={t("login.emailPlaceholder")}
                autoComplete="username"
                className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-[14px] text-slate-900 placeholder:text-slate-400 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50 disabled:text-slate-400"
              />
            </div>

            {/* password */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor="password" className="block text-[13px] font-medium text-slate-700">
                  {t("login.passwordLabel")}
                </label>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    setErr(t("login.forgotPasswordNotAvailable"));
                  }}
                  className="text-[12px] font-medium text-brand-600 hover:text-brand-700"
                >
                  {t("login.forgotPassword")}
                </a>
              </div>
              <div className="relative">
                <input
                  id="password"
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={submitting}
                  placeholder={t("login.passwordPlaceholder")}
                  autoComplete="current-password"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 pr-11 text-[14px] text-slate-900 placeholder:text-slate-400 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50 disabled:text-slate-400"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  disabled={submitting}
                  aria-label={showPw ? t("login.hidePassword") : t("login.showPassword")}
                  className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-2 text-slate-400 transition-colors hover:text-slate-600 disabled:opacity-50"
                >
                  {showPw ? (
                    <EyeOffIcon width={17} height={17} />
                  ) : (
                    <EyeIcon width={17} height={17} />
                  )}
                </button>
              </div>
            </div>

            {/* submit */}
            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-[14px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-brand-600/80"
            >
              {submitting ? (
                <>
                  <span className="spinner" /> {t("login.submitting")}
                </>
              ) : (
                t("login.submit")
              )}
            </button>
          </form>

          <p className="mt-5 text-center text-[12.5px] text-slate-500">{t("login.footerNote")}</p>
        </div>

        {/* footer */}
        <p className="mt-8 text-center text-[11px] text-slate-400">
          {t("common.footerCopyright")} ·{" "}
          <Link to="/login" className="hover:text-slate-500">
            {t("common.privacy")}
          </Link>{" "}
          ·{" "}
          <Link to="/login" className="hover:text-slate-500">
            {t("common.terms")}
          </Link>
        </p>
      </div>
    </div>
  );
}
