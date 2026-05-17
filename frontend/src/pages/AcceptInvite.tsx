import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiAcceptInvite, apiGetInviteInfo } from "../lib/api";
import { AlertCircleIcon, ShieldIcon } from "../components/Icons";

type InviteInfo = Awaited<ReturnType<typeof apiGetInviteInfo>>;

function Field(props: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  autoComplete?: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <div className="mt-4">
      <label htmlFor={props.id} className="mb-1.5 block text-[13px] font-medium text-slate-600">
        {props.label}
        {props.required && <span className="text-red-500"> *</span>}
      </label>
      <input
        id={props.id}
        type={props.type ?? "text"}
        value={props.value}
        required={props.required}
        placeholder={props.placeholder}
        autoComplete={props.autoComplete}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50 disabled:text-slate-400"
      />
      {props.hint && <p className="mt-1 text-[12px] text-slate-400">{props.hint}</p>}
    </div>
  );
}

export function AcceptInvite() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [eofLicenceNo, setEofLicenceNo] = useState("");
  const [phone, setPhone] = useState("");
  const [pharmapiUsername, setPharmapiUsername] = useState("");
  const [pharmapiPassword, setPharmapiPassword] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLoadError("No invitation token found. Please use the link from your invite.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    apiGetInviteInfo(token)
      .then((info) => {
        if (!cancelled) setInvite(info);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load invite.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    if (!token) return;

    if (!fullName.trim() || !eofLicenceNo.trim() || !pharmapiUsername.trim() || !pharmapiPassword) {
      setSubmitError("Please fill in all required fields.");
      return;
    }
    if (password.length < 8) {
      setSubmitError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setSubmitError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      await apiAcceptInvite({
        token,
        full_name: fullName.trim(),
        password,
        eof_licence_no: eofLicenceNo.trim(),
        phone: phone.trim() || undefined,
        pharmapi_username: pharmapiUsername.trim(),
        pharmapi_password: pharmapiPassword,
      });
      navigate("/login", {
        replace: true,
        state: { notice: "Account created — please log in." },
      });
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Failed to create account.");
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-[480px] rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-cardLg">
          <span className="spinner" />
          <p className="mt-3 text-[13px] text-slate-500">Loading your invitation…</p>
        </div>
      </div>
    );
  }

  if (loadError || !invite) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-[480px] rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-cardLg sm:p-10">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-100 text-red-600">
            <AlertCircleIcon width={30} height={30} />
          </div>
          <h1 className="text-xl font-bold text-slate-900">Invitation unavailable</h1>
          <p className="mt-2 text-[13px] leading-relaxed text-slate-500">
            {loadError ?? "This invitation could not be loaded."}
          </p>
          <Link to="/login" className="btn btn-primary mt-6 inline-flex">
            Go to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-[480px] rounded-2xl border border-slate-200 bg-white p-8 shadow-cardLg sm:p-10">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-white">
          <ShieldIcon width={30} height={30} />
        </div>
        <h1 className="text-center text-2xl font-bold text-brand-600">PharmAssist</h1>
        <p className="mt-1.5 text-center text-[13px] leading-relaxed text-slate-500">
          Complete your pharmacist registration
        </p>

        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            You are joining
          </p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">{invite.pharmacy_name}</p>
          {invite.pharmacy_address && (
            <p className="text-[13px] text-slate-500">{invite.pharmacy_address}</p>
          )}
          <p className="mt-1 text-[13px] text-slate-500">
            Invitation for <span className="font-medium text-slate-700">{invite.email}</span>
          </p>
        </div>

        <form onSubmit={onSubmit} noValidate className="mt-6">
          {submitError && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{submitError}</span>
            </div>
          )}

          <Field
            id="fullName"
            label="Full name"
            value={fullName}
            onChange={setFullName}
            required
            autoComplete="name"
            disabled={submitting}
          />
          <Field
            id="password"
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            required
            autoComplete="new-password"
            hint="At least 8 characters."
            disabled={submitting}
          />
          <Field
            id="confirmPassword"
            label="Confirm password"
            type="password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            required
            autoComplete="new-password"
            disabled={submitting}
          />
          <Field
            id="eofLicenceNo"
            label="E.O.Φ. Licence No."
            value={eofLicenceNo}
            onChange={setEofLicenceNo}
            required
            placeholder="ΦΑΡ/12345/2020"
            disabled={submitting}
          />
          <Field
            id="phone"
            label="Phone"
            type="tel"
            value={phone}
            onChange={setPhone}
            autoComplete="tel"
            disabled={submitting}
          />

          <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <h2 className="text-[13px] font-semibold text-slate-700">
              ΗΔΥΚΑ Ηλεκτρονική Συνταγογράφηση
            </h2>
            <Field
              id="pharmapiUsername"
              label="Όνομα χρήστη Ηλεκτρονικής Συνταγογράφησης"
              value={pharmapiUsername}
              onChange={setPharmapiUsername}
              required
              autoComplete="off"
              disabled={submitting}
            />
            <Field
              id="pharmapiPassword"
              label="Κωδικός πρόσβασης Ηλεκτρονικής Συνταγογράφησης"
              type="password"
              value={pharmapiPassword}
              onChange={setPharmapiPassword}
              required
              autoComplete="off"
              disabled={submitting}
            />
            <p className="mt-2.5 text-[12px] leading-relaxed text-slate-500">
              Αυτά είναι τα στοιχεία που χρησιμοποιείτε για τη σύνδεση στη συνταγογράφηση.
            </p>
          </div>

          <button type="submit" disabled={submitting} className="btn btn-primary mt-6 w-full py-3">
            {submitting ? (
              <>
                <span className="spinner" /> Creating account…
              </>
            ) : (
              "Create account"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
