import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { apiAcceptInvite, apiGetInviteInfo } from "../lib/api";
import {
  AlertCircleIcon,
  CheckIcon,
  EyeIcon,
  EyeOffIcon,
  PillIcon,
  ShieldIcon,
} from "../components/Icons";

type InviteInfo = Awaited<ReturnType<typeof apiGetInviteInfo>>;

// Password scoring mirrors 02-accept-invite.html: 4 levels with concrete
// requirements (length / mixed case / number) that the UI surfaces inline.
interface PasswordScore {
  score: 0 | 1 | 2 | 3 | 4;
  checks: { len: boolean; mixed: boolean; num: boolean };
  valid: boolean;
}
function scorePassword(pw: string): PasswordScore {
  const checks = {
    len: pw.length >= 10,
    mixed: /[a-z]/.test(pw) && /[A-Z]/.test(pw),
    num: /[0-9]/.test(pw),
  };
  let score = 0;
  if (pw.length > 0) score = 1;
  if (checks.len) score++;
  if (checks.mixed) score++;
  if (checks.num) score++;
  if (pw.length === 0) score = 0;
  return {
    score: Math.min(score, 4) as PasswordScore["score"],
    checks,
    valid: checks.len && checks.mixed && checks.num,
  };
}

interface StrengthVisual {
  bar: string;
  text: string;
  labelKey: string;
}
const STRENGTH: Record<PasswordScore["score"], StrengthVisual | null> = {
  0: null,
  1: { bar: "bg-red-500", text: "text-red-600", labelKey: "acceptInvite.passwordStrengthWeak" },
  2: {
    bar: "bg-amber-500",
    text: "text-amber-600",
    labelKey: "acceptInvite.passwordStrengthFair",
  },
  3: {
    bar: "bg-brand-500",
    text: "text-brand-600",
    labelKey: "acceptInvite.passwordStrengthGood",
  },
  4: {
    bar: "bg-emerald-500",
    text: "text-emerald-600",
    labelKey: "acceptInvite.passwordStrengthStrong",
  },
};

function BrandHeader() {
  const { t } = useTranslation();
  return (
    <div className="mb-8 flex flex-col items-center text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-card">
        <PillIcon width={26} height={26} />
      </div>
      <div className="mt-3 text-2xl font-bold tracking-tight text-brand-600">
        {t("common.appName")}
      </div>
    </div>
  );
}

function Requirement({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <li
      className={`flex items-center gap-1.5 transition-colors ${
        ok ? "text-emerald-600" : "text-slate-400"
      }`}
    >
      <span
        className={`flex h-3.5 w-3.5 items-center justify-center rounded-full ${
          ok ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-300"
        }`}
      >
        <CheckIcon width={10} height={10} strokeWidth={3} />
      </span>
      {children}
    </li>
  );
}

function PageShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-slate-50 px-4 py-16">
      {children}
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
  );
}

// ─── Loading shell ──────────────────────────────────────────────────────────
function LoadingState() {
  const { t } = useTranslation();
  return (
    <PageShell>
      <div className="w-full max-w-[440px] animate-fade-in">
        <BrandHeader />
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-cardLg">
          <span className="spinner" />
          <p className="mt-3 text-[13px] text-slate-500">{t("acceptInvite.loading")}</p>
        </div>
      </div>
    </PageShell>
  );
}

// ─── Invalid / expired token ────────────────────────────────────────────────
function InvalidToken({ message }: { message?: string }) {
  const { t } = useTranslation();
  return (
    <PageShell>
      <div className="w-full max-w-[440px] animate-fade-in">
        <BrandHeader />
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-cardLg">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
            <AlertCircleIcon width={24} height={24} />
          </div>
          <h1 className="mt-4 text-lg font-bold text-slate-900">
            {t("acceptInvite.invalidTitle")}
          </h1>
          <p className="mx-auto mt-2 max-w-[320px] text-[13px] leading-relaxed text-slate-500">
            {message ?? t("acceptInvite.invalidBody")}
          </p>
          <Link
            to="/login"
            className="mt-6 inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-700 shadow-card transition-colors hover:bg-slate-50"
          >
            {t("acceptInvite.backToSignIn")}
          </Link>
        </div>
      </div>
    </PageShell>
  );
}

// ─── Valid invite — registration form ───────────────────────────────────────
interface InviteFormProps {
  token: string;
  invite: InviteInfo;
}

function InviteForm({ token, invite }: InviteFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [agree, setAgree] = useState(false);

  const [eofLicenceNo, setEofLicenceNo] = useState("");
  const [phone, setPhone] = useState("");
  const [pharmapiUsername, setPharmapiUsername] = useState("");
  const [pharmapiPassword, setPharmapiPassword] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const s = scorePassword(pw);
  const strengthVisual = STRENGTH[s.score];
  const match = confirm.length > 0 && confirm === pw;
  const canSubmit =
    fullName.trim().length > 1 &&
    s.valid &&
    match &&
    agree &&
    eofLicenceNo.trim().length > 0 &&
    pharmapiUsername.trim().length > 0 &&
    pharmapiPassword.length > 0 &&
    !submitting;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    if (!fullName.trim() || !eofLicenceNo.trim() || !pharmapiUsername.trim() || !pharmapiPassword) {
      setSubmitError(t("acceptInvite.missingFieldsError"));
      return;
    }
    if (!s.valid) {
      setSubmitError(t("acceptInvite.passwordRequirementsError"));
      return;
    }
    if (pw !== confirm) {
      setSubmitError(t("acceptInvite.passwordsDontMatchError"));
      return;
    }
    setSubmitting(true);
    try {
      await apiAcceptInvite({
        token,
        full_name: fullName.trim(),
        password: pw,
        eof_licence_no: eofLicenceNo.trim(),
        phone: phone.trim() || undefined,
        pharmapi_username: pharmapiUsername.trim(),
        pharmapi_password: pharmapiPassword,
      });
      navigate("/login", {
        replace: true,
        state: { notice: t("acceptInvite.createdNotice") },
      });
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : t("acceptInvite.createFailed"));
      setSubmitting(false);
    }
  }

  return (
    <PageShell>
      <div className="w-full max-w-[440px] animate-fade-in">
        <BrandHeader />
        <div className="rounded-xl border border-slate-200 bg-white p-7 shadow-cardLg">
          <h1 className="text-lg font-bold text-slate-900">{t("acceptInvite.welcomeTitle")}</h1>

          {/* Inviting-pharmacy context block — brand-50 tint, ShieldIcon */}
          <div className="mt-4 flex items-start gap-3 rounded-lg border border-brand-100 bg-brand-50 px-4 py-3.5">
            <span className="mt-0.5 shrink-0 text-brand-600">
              <ShieldIcon width={18} height={18} />
            </span>
            <p className="text-[13px] leading-relaxed text-slate-700">
              <Trans
                i18nKey="acceptInvite.invitedBy"
                values={{ pharmacy: invite.pharmacy_name }}
                components={[<span key="pharmacy" className="font-semibold text-slate-900" />]}
              />
              {invite.pharmacy_address && (
                <span className="mt-1 block text-[12px] text-slate-500">
                  {invite.pharmacy_address}
                </span>
              )}
              <span className="mt-1 block text-[12px] text-slate-500">{invite.email}</span>
            </p>
          </div>

          {submitError && (
            <div
              className="mt-4 flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-[13px] text-red-700 animate-alert-in"
              role="alert"
            >
              <span className="mt-0.5 shrink-0 text-red-600">
                <AlertCircleIcon width={16} height={16} />
              </span>
              <span>{submitError}</span>
            </div>
          )}

          <form className="mt-5 space-y-4" onSubmit={onSubmit} noValidate>
            {/* Full name */}
            <div>
              <label
                htmlFor="fullName"
                className="mb-1.5 block text-[13px] font-medium text-slate-700"
              >
                {t("acceptInvite.fullNameLabel")}
              </label>
              <input
                id="fullName"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={submitting}
                className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-[14px] text-slate-900 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50 disabled:text-slate-400"
              />
            </div>

            {/* Password + strength + requirements */}
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-[13px] font-medium text-slate-700"
              >
                {t("acceptInvite.passwordLabel")}
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPw ? "text" : "password"}
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  disabled={submitting}
                  placeholder={t("acceptInvite.passwordPlaceholder")}
                  autoComplete="new-password"
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

              {/* Strength bars */}
              <div className="mt-2.5">
                <div className="flex gap-1.5">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className={`h-1.5 flex-1 rounded-full transition-colors ${
                        strengthVisual && i <= s.score ? strengthVisual.bar : "bg-slate-100"
                      }`}
                    />
                  ))}
                </div>
                {strengthVisual && (
                  <div className={`mt-1.5 text-[11.5px] font-medium ${strengthVisual.text}`}>
                    {t(strengthVisual.labelKey)}
                  </div>
                )}
              </div>

              {/* Requirements */}
              <ul className="mt-2.5 space-y-1 text-[12px]">
                <Requirement ok={s.checks.len}>{t("acceptInvite.passwordReqLength")}</Requirement>
                <Requirement ok={s.checks.mixed}>{t("acceptInvite.passwordReqMixed")}</Requirement>
                <Requirement ok={s.checks.num}>{t("acceptInvite.passwordReqNumber")}</Requirement>
              </ul>
            </div>

            {/* Confirm password */}
            <div>
              <label
                htmlFor="confirm"
                className="mb-1.5 block text-[13px] font-medium text-slate-700"
              >
                {t("acceptInvite.confirmPasswordLabel")}
              </label>
              <input
                id="confirm"
                type={showPw ? "text" : "password"}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={submitting}
                placeholder={t("acceptInvite.confirmPasswordPlaceholder")}
                autoComplete="new-password"
                className={`w-full rounded-lg border bg-white px-3.5 py-2.5 text-[14px] text-slate-900 placeholder:text-slate-400 outline-none transition-colors focus:ring-2 disabled:bg-slate-50 disabled:text-slate-400 ${
                  confirm.length === 0
                    ? "border-slate-200 focus:border-brand-500 focus:ring-brand-100"
                    : match
                      ? "border-emerald-300 focus:border-emerald-500 focus:ring-emerald-100"
                      : "border-red-300 focus:border-red-500 focus:ring-red-100"
                }`}
              />
              {confirm.length > 0 && !match && (
                <div className="mt-1.5 text-[12px] text-red-600">
                  {t("acceptInvite.passwordsDontMatch")}
                </div>
              )}
            </div>

            {/* Pharmacy linking — kept inside the form to preserve the
                apiAcceptInvite contract; visually grouped so it doesn't break
                the welcome-flow hierarchy from the reference design. */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2">
                <h2 className="text-[13px] font-semibold text-slate-700">
                  {t("acceptInvite.pharmacyLinkingTitle")}
                </h2>
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-slate-500">
                {t("acceptInvite.pharmacyLinkingHint")}
              </p>

              <div className="mt-3 space-y-3">
                <div>
                  <label
                    htmlFor="eofLicenceNo"
                    className="mb-1.5 block text-[12.5px] font-medium text-slate-700"
                  >
                    {t("acceptInvite.eofLicenceLabel")}
                  </label>
                  <input
                    id="eofLicenceNo"
                    type="text"
                    value={eofLicenceNo}
                    onChange={(e) => setEofLicenceNo(e.target.value)}
                    disabled={submitting}
                    placeholder={t("acceptInvite.eofLicencePlaceholder")}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[14px] text-slate-900 placeholder:text-slate-400 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-100"
                  />
                </div>

                <div>
                  <label
                    htmlFor="phone"
                    className="mb-1.5 block text-[12.5px] font-medium text-slate-700"
                  >
                    {t("acceptInvite.phoneLabel")}
                  </label>
                  <input
                    id="phone"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    disabled={submitting}
                    autoComplete="tel"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[14px] text-slate-900 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-100"
                  />
                </div>

                <div>
                  <label
                    htmlFor="pharmapiUsername"
                    className="mb-1.5 block text-[12.5px] font-medium text-slate-700"
                  >
                    {t("acceptInvite.pharmapiUsernameLabel")}
                  </label>
                  <input
                    id="pharmapiUsername"
                    type="text"
                    value={pharmapiUsername}
                    onChange={(e) => setPharmapiUsername(e.target.value)}
                    disabled={submitting}
                    autoComplete="off"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[14px] text-slate-900 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-100"
                  />
                </div>

                <div>
                  <label
                    htmlFor="pharmapiPassword"
                    className="mb-1.5 block text-[12.5px] font-medium text-slate-700"
                  >
                    {t("acceptInvite.pharmapiPasswordLabel")}
                  </label>
                  <input
                    id="pharmapiPassword"
                    type="password"
                    value={pharmapiPassword}
                    onChange={(e) => setPharmapiPassword(e.target.value)}
                    disabled={submitting}
                    autoComplete="off"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[14px] text-slate-900 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-100"
                  />
                </div>
              </div>
            </div>

            {/* Agree to terms */}
            <label className="flex cursor-pointer items-start gap-2.5 pt-1">
              <input
                type="checkbox"
                checked={agree}
                onChange={(e) => setAgree(e.target.checked)}
                disabled={submitting}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              />
              <span className="text-[12.5px] leading-relaxed text-slate-600">
                <Trans
                  i18nKey="acceptInvite.agreeTos"
                  components={[
                    <Link
                      key="tos"
                      to="/login"
                      className="font-medium text-brand-600 hover:text-brand-700"
                    />,
                    <Link
                      key="gdpr"
                      to="/login"
                      className="font-medium text-brand-600 hover:text-brand-700"
                    />,
                  ]}
                />
              </span>
            </label>

            <button
              type="submit"
              disabled={!canSubmit}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-[14px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none"
            >
              {submitting ? (
                <>
                  <span className="spinner" /> {t("acceptInvite.submitting")}
                </>
              ) : (
                t("acceptInvite.submit")
              )}
            </button>
          </form>

          <p className="mt-5 text-center text-[12.5px] text-slate-500">
            {t("acceptInvite.alreadyHaveAccount")}{" "}
            <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
              {t("acceptInvite.signInLink")}
            </Link>
          </p>
        </div>
      </div>
    </PageShell>
  );
}

// ─── Page root — orchestrates loading / invalid / valid states ───────────────
export function AcceptInvite() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [loading, setLoading] = useState(true);
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLoadError(t("acceptInvite.missingTokenError"));
      setLoading(false);
      return;
    }
    let cancelled = false;
    apiGetInviteInfo(token)
      .then((info) => {
        if (!cancelled) setInvite(info);
      })
      .catch((e) => {
        if (!cancelled)
          setLoadError(e instanceof Error ? e.message : t("acceptInvite.createFailed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  if (loading) return <LoadingState />;
  if (loadError || !invite) return <InvalidToken message={loadError ?? undefined} />;
  return <InviteForm token={token!} invite={invite} />;
}
