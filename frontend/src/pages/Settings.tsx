import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  UserIcon,
  KeyIcon,
  BuildingIcon,
  UsersIcon,
  ListIcon,
  ShieldOffIcon,
  AlertTriangleIcon,
  RefreshIcon,
  DownloadIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  LockIcon,
  XIcon,
} from "../components/Icons";
import { ApiError, me, invitePharmacist } from "../lib/api";
import { useToast } from "../components/Toast";
import type { MeResponse } from "../lib/api";

type SubPage = "profile" | "credentials" | "pharmacy" | "team" | "audit" | "danger";

// ── small shared bits ─────────────────────────────────────────────────────────

function Card({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-card">
      <h2 className="text-[16px] font-bold text-slate-900 dark:text-slate-100">{title}</h2>
      {desc && <p className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">{desc}</p>}
      <div className="mt-4">{children}</div>
    </div>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: React.ReactNode;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-1 border-b border-slate-100 dark:border-slate-800 py-4 last:border-0 sm:grid-cols-[200px_1fr] sm:items-center sm:gap-4">
      <div>
        <div className="text-[13px] font-semibold text-slate-700 dark:text-slate-300">{label}</div>
        {hint && (
          <div className="mt-0.5 text-[11.5px] text-slate-400 dark:text-slate-500">{hint}</div>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function ReadOnlyTag() {
  const { t } = useTranslation();
  return (
    <span className="ml-2 inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 dark:text-slate-500">
      <LockIcon width={10} height={10} /> {t("settings.readOnly")}
    </span>
  );
}

function FieldInput({
  value,
  readOnly,
  mono,
  placeholder,
  onChange,
}: {
  value: string;
  readOnly?: boolean;
  mono?: boolean;
  placeholder?: string;
  onChange?: (v: string) => void;
}) {
  return (
    <input
      value={value}
      readOnly={readOnly}
      placeholder={placeholder}
      onChange={(e) => onChange?.(e.target.value)}
      className={`w-full max-w-md rounded-lg border px-3 py-2 text-[13.5px] outline-none transition-colors placeholder:text-slate-400 dark:placeholder:text-slate-500 ${
        mono ? "mono" : ""
      } ${
        readOnly
          ? "cursor-not-allowed border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400"
          : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
      }`}
    />
  );
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onClick}
      className={`relative h-6 w-11 rounded-full transition-colors ${on ? "bg-brand-600" : "bg-slate-200 dark:bg-slate-700"}`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? "left-[22px]" : "left-0.5"}`}
      />
    </button>
  );
}

function ComingSoonBadge() {
  const { t } = useTranslation();
  return (
    <span className="ml-2 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 dark:text-slate-500">
      {t("settings.comingSoon")}
    </span>
  );
}

// ── Update-password modal ─────────────────────────────────────────────────────

function PwModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 animate-fade-in bg-slate-900/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-[420px] animate-modal-in rounded-2xl bg-white dark:bg-slate-900 p-6 shadow-modal">
        <div className="flex items-center justify-between">
          <h3 className="text-[16px] font-bold text-slate-900 dark:text-slate-100">
            {t("settings.pwModalTitle")}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <XIcon width={18} height={18} />
          </button>
        </div>
        <p className="mt-1 text-[12.5px] text-slate-500 dark:text-slate-400">
          {t("settings.pwModalDesc")}
        </p>
        <div className="mt-4 space-y-3">
          {[
            [t("settings.pwCurrent"), current, setCurrent],
            [t("settings.pwNew"), next, setNext],
            [t("settings.pwConfirm"), confirm, setConfirm],
          ].map(([label, val, setter]) => (
            <label key={label as string} className="block">
              <span className="mb-1 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
                {label as string}
              </span>
              <input
                type="password"
                value={val as string}
                onChange={(e) => (setter as (v: string) => void)(e.target.value)}
                className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              />
            </label>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/60"
          >
            {t("settings.cancel")}
          </button>
          <button
            type="button"
            onClick={() => {
              toast("Password update is coming soon.", "info");
              onClose();
            }}
            disabled={!current || !next || next !== confirm}
            className="rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {t("settings.updatePassword")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ── sub-pages ─────────────────────────────────────────────────────────────────

function ProfilePage({ profile, onSave }: { profile: MeResponse | null; onSave: () => void }) {
  const { t, i18n } = useTranslation();
  const [lang, setLang] = useState(() => (i18n.language === "en" ? "EN" : "EL"));
  const [notifs, setNotifs] = useState({ a: true, b: true, c: false, d: true });

  return (
    <div className="space-y-5">
      <Card title={t("settings.profileTitle")} desc={t("settings.profileDesc")}>
        <Row label={t("settings.fieldName")}>
          <FieldInput value={profile?.name ?? ""} placeholder="—" readOnly />
        </Row>
        <Row label={t("settings.fieldEmail")}>
          <FieldInput value={profile?.email ?? ""} placeholder="—" readOnly />
        </Row>
        <Row
          label={
            <>
              {t("settings.fieldLicence")} <ReadOnlyTag />
            </>
          }
        >
          <FieldInput value="—" readOnly mono />
        </Row>
        <Row label={t("settings.fieldLanguage")}>
          <div className="flex w-fit items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-0.5">
            {[
              ["EL", "Ελληνικά"],
              ["EN", "English"],
            ].map(([v, l]) => (
              <button
                key={v}
                type="button"
                onClick={() => {
                  setLang(v);
                  void i18n.changeLanguage(v.toLowerCase());
                }}
                className={`rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  lang === v
                    ? "bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-card"
                    : "text-slate-500 dark:text-slate-400"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </Row>
      </Card>

      <Card title={t("settings.notifTitle")} desc={t("settings.notifDesc")}>
        {[
          {
            label: t("settings.notifSafetyAlerts"),
            inApp: notifs.a,
            email: notifs.b,
            onA: () => setNotifs((s) => ({ ...s, a: !s.a })),
            onE: () => setNotifs((s) => ({ ...s, b: !s.b })),
          },
          {
            label: t("settings.notifAdrAck"),
            inApp: notifs.c,
            email: notifs.d,
            onA: () => setNotifs((s) => ({ ...s, c: !s.c })),
            onE: () => setNotifs((s) => ({ ...s, d: !s.d })),
          },
          {
            label: t("settings.notifHdykaExpiry"),
            inApp: true,
            email: false,
            onA: () => {},
            onE: () => {},
          },
        ].map(({ label, inApp, email, onA, onE }) => (
          <div
            key={label}
            className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 py-3 last:border-0"
          >
            <span className="text-[13px] text-slate-700 dark:text-slate-300">{label}</span>
            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 text-[12px] text-slate-500 dark:text-slate-400">
                {t("settings.notifInApp")} <Toggle on={inApp} onClick={onA} />
              </label>
              <label className="flex items-center gap-2 text-[12px] text-slate-500 dark:text-slate-400">
                {t("settings.notifEmail")} <Toggle on={email} onClick={onE} />
              </label>
            </div>
          </div>
        ))}
      </Card>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onSave}
          className="rounded-lg bg-brand-600 px-5 py-2.5 text-[13px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700"
        >
          {t("settings.saveChanges")}
        </button>
      </div>
    </div>
  );
}

function CredentialsPage({
  profile,
  onUpdatePw,
}: {
  profile: MeResponse | null;
  onUpdatePw: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      <Card title={t("settings.credentialsTitle")} desc={t("settings.credentialsDesc")}>
        <Row
          label={
            <>
              {t("settings.fieldUsername")} <ReadOnlyTag />
            </>
          }
        >
          <FieldInput value={profile?.pharmacist_id ?? "—"} readOnly mono />
        </Row>
        <Row label={t("settings.fieldPassword")} hint={t("settings.fieldPasswordHint")}>
          <button
            type="button"
            onClick={onUpdatePw}
            className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-700 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
          >
            {t("settings.updatePassword")}
          </button>
        </Row>
      </Card>

      <Card title={t("settings.sessionTitle")} desc={t("settings.sessionDesc")}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-[13px] text-slate-600 dark:text-slate-300">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            {t("settings.sessionActive")}{" "}
            <span className="mono">{new Date().toLocaleDateString()}</span>
          </div>
          <button
            type="button"
            disabled
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3.5 py-2 text-[13px] font-semibold text-brand-600 dark:text-brand-400 opacity-50 transition-colors hover:bg-brand-50 dark:hover:bg-brand-500/10"
          >
            <RefreshIcon width={15} height={15} /> {t("settings.refreshSession")}
            <ComingSoonBadge />
          </button>
        </div>
      </Card>
    </div>
  );
}

function PharmacyPage({ profile }: { profile: MeResponse | null }) {
  const { t } = useTranslation();
  return (
    <Card title={t("settings.pharmacyTitle")} desc={t("settings.pharmacyDesc")}>
      <Row
        label={
          <>
            {t("settings.fieldPharmacyName")} <ReadOnlyTag />
          </>
        }
      >
        <FieldInput value={profile?.pharmacy ?? "—"} readOnly />
      </Row>
      <Row
        label={
          <>
            {t("settings.fieldCategory")} <ReadOnlyTag />
          </>
        }
        hint={t("settings.fieldCategoryHint")}
      >
        <span className="inline-flex items-center rounded-full bg-brand-50 dark:bg-brand-500/15 px-3 py-1 text-[12.5px] font-semibold text-brand-700 dark:text-brand-300">
          {t("settings.categoryEopyyContracted")}
        </span>
      </Row>
      <Row label={t("settings.fieldVat")}>
        <FieldInput value="" placeholder="—" readOnly />
      </Row>
      <Row label={t("settings.fieldTaxOffice")}>
        <FieldInput value="" placeholder="—" readOnly />
      </Row>
      <Row label={t("settings.fieldAddress")}>
        <FieldInput value="" placeholder="—" readOnly />
      </Row>
    </Card>
  );
}

function TeamPage({
  profile,
  onInvite,
}: {
  profile: MeResponse | null;
  onInvite: (email: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const { toast } = useToast();

  async function handleInvite() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await onInvite(inviteEmail.trim());
      toast(`Invite sent to ${inviteEmail}`, "success");
      setInviteEmail("");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Invite failed.", "error");
    } finally {
      setInviting(false);
    }
  }

  const teamMembers = profile
    ? [{ name: profile.name, email: profile.email, role: "Admin", you: true }]
    : [];

  return (
    <Card title={t("settings.teamTitle")} desc={t("settings.teamDesc")}>
      {/* invite form */}
      <div className="mb-4 flex gap-2">
        <input
          value={inviteEmail}
          onChange={(e) => setInviteEmail(e.target.value)}
          placeholder={t("settings.inviteEmail")}
          className="flex-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
        <button
          type="button"
          onClick={handleInvite}
          disabled={!inviteEmail.trim() || inviting}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700 disabled:opacity-50"
        >
          <PlusIcon width={15} height={15} />
          {inviting ? <span className="spinner" /> : t("settings.inviteSend")}
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
        {teamMembers.length === 0 ? (
          <div className="px-4 py-6 text-center text-[13px] text-slate-500 dark:text-slate-400">
            <span className="spinner text-brand-600" /> Loading…
          </div>
        ) : (
          teamMembers.map((m, i) => (
            <div
              key={m.email}
              className={`flex items-center gap-3 px-4 py-3 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800" : ""}`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-[12px] font-bold text-slate-500 dark:text-slate-400">
                {m.name.split(" ")[0][0]}
                {m.name.split(" ")[1]?.[0] ?? ""}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[13.5px] font-semibold text-slate-900 dark:text-slate-100">
                  {m.name}
                  {m.you && (
                    <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:text-slate-400">
                      {t("settings.youBadge")}
                    </span>
                  )}
                </div>
                <div className="text-[12px] text-slate-500 dark:text-slate-400">{m.email}</div>
              </div>
              <span className="rounded-full border border-slate-200 dark:border-slate-800 px-2.5 py-1 text-[12px] font-medium text-slate-600 dark:text-slate-300">
                {m.role}
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

const MOCK_AUDIT = [
  {
    ts: "31/05/2026 14:31:08",
    actor: "—",
    action: "Dispense executed",
    target: "barcode …",
    type: "dispense",
  },
  {
    ts: "31/05/2026 13:58:12",
    actor: "—",
    action: "Patient data accessed",
    target: "AMKA ••••",
    type: "access",
  },
  {
    ts: "31/05/2026 09:02:41",
    actor: "—",
    action: "Login",
    target: "IP 79.x.x.x",
    type: "login",
  },
];

type AuditFilter = "all" | "dispense" | "access" | "login";

function AuditPage() {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<AuditFilter>("all");

  const auditTabs: { value: AuditFilter; label: string }[] = [
    { value: "all", label: t("settings.auditAll") },
    { value: "dispense", label: t("settings.auditDispense") },
    { value: "access", label: t("settings.auditAccess") },
    { value: "login", label: t("settings.auditLogin") },
  ];

  const visibleAudit = filter === "all" ? MOCK_AUDIT : MOCK_AUDIT.filter((a) => a.type === filter);

  const TYPE_TONE: Record<string, string> = {
    dispense: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    access: "bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300",
    login: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300",
  };

  return (
    <Card title={t("settings.auditTitle")} desc={t("settings.auditDesc")}>
      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-0.5">
          {auditTabs.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              className={`rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                filter === value
                  ? "bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-card"
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-[12.5px] font-semibold text-slate-700 dark:text-slate-300 opacity-50 hover:bg-slate-50 dark:hover:bg-slate-800/60"
        >
          <DownloadIcon width={15} height={15} /> {t("settings.auditExport")}
          <ComingSoonBadge />
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
        <div className="grid grid-cols-[170px_140px_1fr_120px] gap-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          <span>{t("settings.colTimestamp")}</span>
          <span>{t("settings.colActor")}</span>
          <span>{t("settings.colAction")}</span>
          <span>{t("settings.colType")}</span>
        </div>
        {visibleAudit.map((a, i) => (
          <div
            key={i}
            className={`grid grid-cols-[170px_140px_1fr_120px] items-center gap-4 px-4 py-3 ${i > 0 ? "border-t border-slate-100 dark:border-slate-800" : ""}`}
          >
            <span className="mono text-[12px] text-slate-500 dark:text-slate-400">{a.ts}</span>
            <span className="text-[12.5px] text-slate-700 dark:text-slate-300">{a.actor}</span>
            <span className="text-[12.5px] text-slate-900 dark:text-slate-100">{a.action}</span>
            <span>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${TYPE_TONE[a.type]}`}
              >
                {a.type}
              </span>
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[12px] text-slate-500 dark:text-slate-400">
          {t("settings.auditShowing", { to: visibleAudit.length, total: "—" })}
        </span>
        <div className="flex gap-1.5">
          <button
            type="button"
            disabled
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-400 dark:text-slate-500"
          >
            <ChevronLeftIcon width={15} height={15} />
          </button>
          <button
            type="button"
            disabled
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-400 dark:text-slate-500"
          >
            <ChevronRightIcon width={15} height={15} />
          </button>
        </div>
      </div>
    </Card>
  );
}

function DangerPage({ onSignOutAll }: { onSignOutAll: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-card">
        <h2 className="text-[16px] font-bold text-slate-900 dark:text-slate-100">
          {t("settings.dangerSessions")}
        </h2>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-md text-[13px] text-slate-500 dark:text-slate-400">
            {t("settings.dangerSessionsDesc")}
          </p>
          <button
            type="button"
            onClick={onSignOutAll}
            className="shrink-0 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2 text-[13px] font-semibold text-slate-700 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
          >
            {t("settings.signOutEverywhere")}
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50/50 dark:bg-red-500/10 p-6">
        <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
          <AlertTriangleIcon width={17} height={17} />
          <h2 className="text-[16px] font-bold">{t("settings.dangerZone")}</h2>
        </div>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-md text-[13px] text-red-700/80 dark:text-red-400/80">
            {t("settings.dangerZoneDesc")}{" "}
            <span className="font-semibold">{t("settings.dangerAdminOnly")}</span>
          </p>
          <button
            type="button"
            disabled
            className="shrink-0 rounded-lg bg-red-600 px-4 py-2 text-[13px] font-semibold text-white opacity-50 shadow-card"
          >
            {t("settings.deleteAccount")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function Settings() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [page, setPage] = useState<SubPage>("profile");
  const [pwOpen, setPwOpen] = useState(false);
  const [profile, setProfile] = useState<MeResponse | null>(null);

  useEffect(() => {
    me()
      .then(setProfile)
      .catch(() => toast("Could not load profile.", "error"));
  }, [toast]);

  const SUBNAV: {
    id: SubPage;
    label: string;
    Icon: typeof UserIcon;
    admin?: boolean;
    danger?: boolean;
  }[] = [
    { id: "profile", label: t("settings.navProfile"), Icon: UserIcon },
    { id: "credentials", label: t("settings.navCredentials"), Icon: KeyIcon },
    { id: "pharmacy", label: t("settings.navPharmacy"), Icon: BuildingIcon },
    { id: "team", label: t("settings.navTeam"), Icon: UsersIcon, admin: true },
    { id: "audit", label: t("settings.navAudit"), Icon: ListIcon },
    { id: "danger", label: t("settings.navDanger"), Icon: ShieldOffIcon, danger: true },
  ];

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-8 lg:px-8">
      {pwOpen && <PwModal onClose={() => setPwOpen(false)} />}

      <div className="mb-6">
        <h1 className="text-[24px] font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("settings.title")}
        </h1>
        <p className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">
          {t("settings.subtitle")}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-7 lg:grid-cols-[210px_1fr]">
        {/* sub-nav */}
        <nav className="flex flex-row flex-wrap gap-1 lg:flex-col">
          {SUBNAV.map(({ id, label, Icon, admin, danger }) => (
            <button
              key={id}
              type="button"
              onClick={() => setPage(id)}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition-colors ${
                page === id
                  ? danger
                    ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400"
                    : "bg-brand-100 dark:bg-brand-500/15 text-brand-700 dark:text-brand-300"
                  : danger
                    ? "text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              }`}
            >
              <Icon width={16} height={16} />
              <span className="flex-1">{label}</span>
              {admin && (
                <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[9.5px] font-bold uppercase text-slate-400 dark:text-slate-500">
                  {t("settings.adminBadge")}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* panel */}
        <div className="min-w-0 animate-fade-in" key={page}>
          {page === "profile" && (
            <ProfilePage
              profile={profile}
              onSave={() => toast("Coming soon — profile editing is not yet available.", "info")}
            />
          )}
          {page === "credentials" && (
            <CredentialsPage profile={profile} onUpdatePw={() => setPwOpen(true)} />
          )}
          {page === "pharmacy" && <PharmacyPage profile={profile} />}
          {page === "team" && (
            <TeamPage
              profile={profile}
              onInvite={async (email) => {
                await invitePharmacist(email);
              }}
            />
          )}
          {page === "audit" && <AuditPage />}
          {page === "danger" && (
            <DangerPage onSignOutAll={() => toast("Signed out on all other devices.", "success")} />
          )}
        </div>
      </div>
    </div>
  );
}
