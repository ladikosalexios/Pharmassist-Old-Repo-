import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircleIcon,
  AlertOctagonIcon,
  AlertTriangleIcon,
  ArrowLeftIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  InfoIcon,
  PlusIcon,
  EditIcon,
  TrashIcon,
  XIcon,
} from "../components/Icons";
import {
  ApiError,
  apiErrorI18nKey,
  createPatientCondition,
  deletePatientCondition,
  getPatient,
  getPatientConditions,
  getPatientPrescriptions,
  getPatientSideEffects,
  updatePatientCondition,
} from "../lib/api";
import { fallbackForPatient, isProfileShapeIncomplete } from "../lib/patientFallback";
import {
  type PatientProfile as Profile,
  type PatientIntolerance,
  type PatientRxHistoryRow,
  type SideEffectReport,
  PatientCondition,
} from "../types";

// ── tiny helpers ──────────────────────────────────────────────────────────────

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

// Intolerances arrive as plain strings (mock) or as ΗΔΥΚΑ objects
// ({activeSubstance, intolerance, remarks}). Render a substance label + the
// optional intolerance-type detail — NEVER the raw object (that crashes React).
function intoleranceLabel(item: string | PatientIntolerance): { name: string; detail?: string } {
  if (typeof item === "string") return { name: item };
  const name = item.activeSubstance || item.intolerance || "—";
  const detail = item.activeSubstance ? item.intolerance || undefined : undefined;
  return { name, detail };
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatDateShort(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

function Skl({ w = "100%", h = 14, mt = 0 }: { w?: string; h?: number; mt?: number }) {
  return (
    <div className="sk animate-shimmer rounded" style={{ width: w, height: h, marginTop: mt }} />
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      {children}
    </div>
  );
}

function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[15px] font-bold text-slate-900 dark:text-slate-100">{children}</h2>
      {right}
    </div>
  );
}

function Field({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {label}
      </dt>
      <dd
        className={`mt-0.5 text-[13.5px] text-slate-800 dark:text-slate-200 ${mono ? "mono" : ""}`}
      >
        {children}
      </dd>
    </div>
  );
}

// ── Condition Modal (add / edit) ──────────────────────────────────────────────

const CONDITION_CODES = ["G6PD", "PREGNANCY", "RENAL_SEVERE", "HEPATIC"] as const;
const CONDITION_SEVERITIES = ["MILD", "MODERATE", "SEVERE"] as const;

function ConditionModal({
  patientId,
  existing,
  onClose,
  onSaved,
}: {
  patientId: string;
  existing: PatientCondition | null;
  onClose: () => void;
  onSaved: (saved: PatientCondition) => void;
}) {
  const { t } = useTranslation();
  const [conditionCode, setConditionCode] = useState(existing?.conditionCode ?? CONDITION_CODES[0]);
  const [name, setName] = useState(existing?.name ?? "");
  const [severity, setSeverity] = useState(existing?.severity ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seeded conditions may carry a code outside our known list — keep it
  // selectable so editing them doesn't silently rewrite the code.
  const codeOptions: string[] = CONDITION_CODES.includes(
    conditionCode as (typeof CONDITION_CODES)[number],
  )
    ? [...CONDITION_CODES]
    : [conditionCode, ...CONDITION_CODES];
  const codeLabel = (code: string) =>
    CONDITION_CODES.includes(code as (typeof CONDITION_CODES)[number])
      ? t(`patientProfile.conditionCode${code}`)
      : code;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        conditionCode,
        name: name.trim(),
        severity: severity || null,
        notes: notes.trim() || null,
      };
      const saved = existing
        ? await updatePatientCondition(patientId, existing.id, payload)
        : await createPatientCondition(patientId, payload);
      onSaved(saved);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("patientProfile.conditionSaveError"));
      setSaving(false);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 animate-fade-in bg-slate-900/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-[440px] animate-modal-in rounded-2xl bg-white p-6 shadow-modal dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <h3 className="text-[16px] font-bold text-slate-900 dark:text-slate-100">
            {existing
              ? t("patientProfile.editConditionTitle")
              : t("patientProfile.addConditionTitle")}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:text-slate-500 dark:hover:bg-slate-800"
            aria-label={t("patientProfile.cancel")}
          >
            <XIcon width={18} height={18} />
          </button>
        </div>
        <p className="mt-1 text-[12.5px] text-slate-500 dark:text-slate-400">
          {t("patientProfile.addConditionSubtitle")}
        </p>
        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
              {t("patientProfile.conditionCode")}
            </span>
            <select
              value={conditionCode}
              onChange={(e) => setConditionCode(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              {codeOptions.map((code) => (
                <option key={code} value={code}>
                  {codeLabel(code)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
              {t("patientProfile.conditionDesc")}
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("patientProfile.conditionDescPlaceholder")}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
              {t("patientProfile.conditionSeverity")}
            </span>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              <option value="">{t("patientProfile.conditionSeverityNone")}</option>
              {CONDITION_SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {t(`patientProfile.conditionSeverity${s}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-slate-600 dark:text-slate-300">
              {t("patientProfile.conditionNotes")}
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>
        </div>
        {error && (
          <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11.5px] text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
            {error}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800/60"
          >
            {t("patientProfile.cancel")}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!name.trim() || saving}
            className="rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {t("patientProfile.save")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ── History row ───────────────────────────────────────────────────────────────

function HistoryRow({ row, index }: { row: PatientRxHistoryRow; index: number }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const dispensedHere = row.status === "COMPLETED";

  return (
    <div className={`relative pl-7 ${index > 0 ? "pt-5" : ""}`}>
      <span className="absolute left-[5px] top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-500 shadow dark:border-slate-900" />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mono text-[11.5px] text-slate-400 dark:text-slate-500">{row.date}</div>
          <div className="mt-0.5 text-[13.5px] font-semibold text-slate-900 dark:text-slate-100">
            {row.drugName}
          </div>
          <div
            className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              dispensedHere
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            }`}
          >
            <CheckCircleIcon width={12} height={12} />
            {dispensedHere
              ? t("patientProfile.dispensedHere")
              : t("patientProfile.dispensedElsewhere")}
          </div>
          {open && row.prescriberName && (
            <p className="mt-2 text-[12.5px] text-slate-500 dark:text-slate-400">
              {t("patientProfile.prescriberLabel")} {row.prescriberName} · Rx{" "}
              <Link
                to={`/prescription/${row.rxId}`}
                className="text-brand-600 hover:underline dark:text-brand-400"
                onClick={(e) => e.stopPropagation()}
              >
                {row.rxId}
              </Link>
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex shrink-0 items-center gap-0.5 text-[12px] font-semibold text-brand-600 dark:text-brand-400"
        >
          {t("patientProfile.details")}{" "}
          <span className={`transition-transform ${open ? "rotate-180" : ""}`}>
            <ChevronDownIcon width={13} height={13} />
          </span>
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type FilterKey = "all" | "last90" | "lastYear" | "byDrug";

function applyHistoryFilter(rows: PatientRxHistoryRow[], filter: FilterKey): PatientRxHistoryRow[] {
  const now = new Date();
  if (filter === "last90") {
    const cutoff = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
    return rows.filter((r) => new Date(r.date) >= cutoff);
  }
  if (filter === "lastYear") {
    const cutoff = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
    return rows.filter((r) => new Date(r.date) >= cutoff);
  }
  if (filter === "byDrug") {
    const seen = new Set<string>();
    return rows
      .slice()
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      .filter((r) => {
        if (seen.has(r.drugName)) return false;
        seen.add(r.drugName);
        return true;
      });
  }
  return rows;
}

export function PatientProfile() {
  const { id = "" } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const fromRx = search.get("from");
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  const [rxHistory, setRxHistory] = useState<PatientRxHistoryRow[] | null>(null);
  const [rxError, setRxError] = useState<string | null>(null);

  // kept for future ADR section
  const [, setAdrHistory] = useState<SideEffectReport[] | null>(null);

  const [conditions, setConditions] = useState<PatientCondition[] | null>(null);
  const [conditionsError, setConditionsError] = useState<string | null>(null);

  const [usingFallback, setUsingFallback] = useState(false);
  // null = closed; { existing: null } = add; { existing: c } = edit
  const [conditionModal, setConditionModal] = useState<{
    existing: PatientCondition | null;
  } | null>(null);
  const [removingConditionId, setRemovingConditionId] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState<FilterKey>("all");

  function handleConditionSaved(saved: PatientCondition) {
    setConditions((prev) => {
      const list = prev ?? [];
      const idx = list.findIndex((c) => c.id === saved.id);
      if (idx >= 0) {
        const next = list.slice();
        next[idx] = saved;
        return next;
      }
      return [saved, ...list];
    });
  }

  async function handleRemoveCondition(condition: PatientCondition) {
    setRemovingConditionId(condition.id);
    setConditionsError(null);
    try {
      await deletePatientCondition(id, condition.id);
      setConditions((prev) => (prev ?? []).filter((c) => c.id !== condition.id));
    } catch (e) {
      setConditionsError(
        e instanceof ApiError ? e.message : t("patientProfile.removeConditionError"),
      );
    } finally {
      setRemovingConditionId(null);
    }
  }

  useEffect(() => {
    let active = true;
    setProfileLoading(true);
    setProfileError(null);
    setProfile(null);
    setRxHistory(null);
    setAdrHistory(null);
    setRxError(null);
    setConditionsError(null);
    setUsingFallback(false);

    const fb = fallbackForPatient(id);

    getPatient(id)
      .then((data) => {
        if (!active) return;
        if (isProfileShapeIncomplete(data) && fb) {
          setProfile(fb.profile);
          setUsingFallback(true);
        } else {
          setProfile(data);
        }
      })
      .catch((e: unknown) => {
        if (!active) return;
        if (fb) {
          setProfile(fb.profile);
          setUsingFallback(true);
        } else {
          console.error(e);
          setProfileError(t(apiErrorI18nKey(e)));
        }
      })
      .finally(() => {
        if (active) setProfileLoading(false);
      });

    getPatientPrescriptions(id)
      .then((items) => {
        if (active) setRxHistory(items);
      })
      .catch((e: unknown) => {
        if (!active) return;
        if (fb) {
          setRxHistory(fb.rxHistory);
          setUsingFallback(true);
        } else {
          console.error(e);
          setRxError(t(apiErrorI18nKey(e)));
        }
      });

    getPatientSideEffects(id)
      .then((items) => {
        if (active) setAdrHistory(items);
      })
      .catch(() => {
        if (!active) return;
        if (fb) {
          setAdrHistory(fb.adrHistory);
          setUsingFallback(true);
        }
      });

    getPatientConditions(id)
      .then((data) => {
        if (!active) return;
        setConditions(data);
      })
      .catch((e: unknown) => {
        if (!active) return;
        if (fb) {
          setConditions(fb.conditions);
          setUsingFallback(true);
        } else {
          console.error(e);
          setConditionsError(t(apiErrorI18nKey(e)));
        }
      });

    return () => {
      active = false;
    };
  }, [id, t]);

  // ── early states ──
  if (profileLoading) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8 lg:px-8">
        <div className="mb-6 h-5 w-32 sk animate-shimmer rounded" />
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-cardLg dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 shrink-0 sk animate-shimmer rounded-full" />
            <div className="flex-1">
              <Skl w="55%" h={22} />
              <Skl w="40%" h={13} mt={10} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (profileError || !profile) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8 lg:px-8">
        <Link
          to="/patients"
          className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ArrowLeftIcon width={15} height={15} /> {t("patientProfile.backToPatients")}
        </Link>
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-5 dark:border-red-500/30 dark:bg-red-500/10">
          <div className="flex items-start gap-2 text-red-700 dark:text-red-400">
            <AlertCircleIcon className="mt-0.5 shrink-0" />
            <span>{profileError ?? t("patientProfile.profileUnavailable")}</span>
          </div>
        </div>
      </div>
    );
  }

  const intolerances = profile.intolerances ?? [];
  const amka = profile.amka ?? id;
  const filteredHistory: PatientRxHistoryRow[] = rxHistory
    ? applyHistoryFilter(rxHistory, historyFilter)
    : [];

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-6 lg:px-8">
      {conditionModal && (
        <ConditionModal
          patientId={id}
          existing={conditionModal.existing}
          onClose={() => setConditionModal(null)}
          onSaved={handleConditionSaved}
        />
      )}

      {/* back link */}
      {fromRx ? (
        <Link
          to={`/prescription/${fromRx}`}
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-slate-500 transition-colors hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ArrowLeftIcon width={15} height={15} /> {t("patientProfile.backToRx", { rxId: fromRx })}
        </Link>
      ) : (
        <Link
          to="/patients"
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-slate-500 transition-colors hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ArrowLeftIcon width={15} height={15} /> {t("patientProfile.backToPatients")}
        </Link>
      )}

      {usingFallback && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{t("patientProfile.fallbackBanner")}</span>
        </div>
      )}

      {/* ── HEADER STRIP ── */}
      <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-cardLg dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[20px] font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
              {initials(profile.name)}
            </div>
            <div className="min-w-0">
              <h1 className="text-[24px] font-bold tracking-tight text-slate-900 dark:text-slate-100">
                {profile.name}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-slate-500 dark:text-slate-400">
                {amka && <span className="mono">AMKA {amka}</span>}
                {typeof profile.age === "number" && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span>
                      {profile.age} {t("patientProfile.yearsAbbr")}
                    </span>
                  </>
                )}
                {profile.sex && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span>
                      {profile.sex === "F"
                        ? t("patientProfile.sexFemale")
                        : profile.sex === "M"
                          ? t("patientProfile.sexMale")
                          : profile.sex}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => navigate(`/side-effects`)}
              className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[13px] font-semibold text-slate-700 shadow-card transition-colors hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800/60"
            >
              {t("patientProfile.reportSideEffect")}
            </button>
            <button
              type="button"
              onClick={() => navigate(`/documentation`)}
              className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-[13px] font-semibold text-slate-700 shadow-card transition-colors hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800/60"
            >
              {t("patientProfile.viewDocumentation")}
            </button>
            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[13px] font-semibold text-white shadow-card transition-colors hover:bg-brand-700"
            >
              {t("patientProfile.reviewPrescription")} <ChevronRightIcon width={15} height={15} />
            </button>
          </div>
        </div>
      </div>

      {/* ── DEMOGRAPHICS ── */}
      <div className="mt-6">
        <Card>
          <SectionTitle>{t("patientProfile.demographicsTitle")}</SectionTitle>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3">
            <Field label={t("patientProfile.fieldDateOfBirth")} mono>
              {profile.dateOfBirth ? formatDateShort(profile.dateOfBirth) : "—"}
            </Field>
            <Field label={t("patientProfile.fieldSex")}>
              {!profile.sex
                ? "—"
                : profile.sex === "F"
                  ? t("patientProfile.sexFemale")
                  : profile.sex === "M"
                    ? t("patientProfile.sexMale")
                    : profile.sex}
            </Field>
            <Field label={t("patientProfile.fieldNationality")}>{profile.nationality ?? "—"}</Field>
            <Field label={t("patientProfile.fieldPhone")} mono>
              {profile.phone ?? "—"}
            </Field>
            <Field label={t("patientProfile.fieldEmail")}>{profile.email ?? "—"}</Field>
            <Field label={t("patientProfile.fieldAddress")}>{profile.address ?? "—"}</Field>
          </dl>

          {/* safety exceptions as chips */}
          {profile.safetyFlags && (
            <div className="mt-4 flex flex-wrap gap-2">
              {profile.safetyFlags.g6pd && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-[12px] font-medium text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
                  <AlertOctagonIcon width={13} height={13} /> {t("patientProfile.g6pdFlag")}
                </span>
              )}
              {profile.safetyFlags.pregnancyWeeks != null &&
                profile.safetyFlags.pregnancyWeeks > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[12px] font-medium text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
                    <InfoIcon width={13} height={13} />{" "}
                    {t("patientProfile.pregnancyFlag", {
                      weeks: profile.safetyFlags.pregnancyWeeks,
                    })}
                  </span>
                )}
              {profile.safetyFlags.renalFunction &&
                profile.safetyFlags.renalFunction !== "NORMAL" && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[12px] font-medium text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
                    <InfoIcon width={13} height={13} />{" "}
                    {t("patientProfile.renalFlag", {
                      value: profile.safetyFlags.renalFunction.replace(/_/g, " ").toLowerCase(),
                    })}
                  </span>
                )}
              {profile.safetyFlags.hepaticFunction &&
                profile.safetyFlags.hepaticFunction !== "NORMAL" && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[12px] font-medium text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
                    <InfoIcon width={13} height={13} />{" "}
                    {t("patientProfile.hepaticFlag", {
                      value: profile.safetyFlags.hepaticFunction.replace(/_/g, " ").toLowerCase(),
                    })}
                  </span>
                )}
            </div>
          )}

          {/* allergies info banner */}
          {profile.allergies && profile.allergies.length > 0 && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-brand-100 bg-brand-50 px-3.5 py-2.5 dark:border-brand-500/20 dark:bg-brand-500/10">
              <InfoIcon
                width={15}
                height={15}
                className="mt-0.5 shrink-0 text-brand-600 dark:text-brand-400"
              />
              <div className="text-[12.5px] leading-snug text-slate-700 dark:text-slate-300">
                <span className="font-semibold text-brand-700 dark:text-brand-400">
                  {t("patientProfile.allergiesLabel")} ·{" "}
                </span>
                {profile.allergies.join(", ")}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* ── INTOLERANCES + CONDITIONS (2-col) ── */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Intolerances */}
        <Card>
          <SectionTitle
            right={
              intolerances.length > 0 && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11.5px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  {intolerances.length}
                </span>
              )
            }
          >
            {t("patientProfile.intolerancesTitle")}
          </SectionTitle>

          {intolerances.length === 0 ? (
            <p className="py-6 text-center text-[13px] italic text-slate-400 dark:text-slate-500">
              {t("patientProfile.noIntolerances")}
            </p>
          ) : (
            <div className="-mx-1 max-h-[340px] space-y-2 overflow-y-auto px-1">
              {intolerances.map((item, i) => {
                const { name, detail } = intoleranceLabel(item);
                return (
                  <div
                    key={i}
                    className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-500/30 dark:bg-amber-500/10"
                  >
                    <div className="flex items-center gap-2">
                      <AlertTriangleIcon
                        width={14}
                        height={14}
                        className="shrink-0 text-amber-500 dark:text-amber-400"
                      />
                      <span className="mono text-[12.5px] font-bold text-slate-800 dark:text-slate-200">
                        {name}
                      </span>
                    </div>
                    {detail && (
                      <div className="mt-1 pl-6 text-[11.5px] leading-snug text-amber-700/80 dark:text-amber-400/70">
                        {detail}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Conditions */}
        <Card>
          <SectionTitle
            right={
              <button
                type="button"
                onClick={() => setConditionModal({ existing: null })}
                className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[12px] font-semibold text-brand-600 transition-colors hover:bg-brand-50 dark:border-slate-800 dark:bg-slate-900 dark:text-brand-400 dark:hover:bg-brand-500/10"
              >
                <PlusIcon width={13} height={13} /> {t("patientProfile.addCondition")}
              </button>
            }
          >
            {t("patientProfile.conditionsTitle")}{" "}
            <span className="font-normal text-slate-400 dark:text-slate-500">
              {t("patientProfile.conditionsSubtitle")}
            </span>
          </SectionTitle>

          {conditionsError ? (
            <div className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12.5px] text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
              <AlertCircleIcon width={14} height={14} className="shrink-0" />
              {conditionsError}
            </div>
          ) : conditions === null ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i}>
                  <Skl w="55%" h={13} />
                  <Skl w="40%" h={11} mt={6} />
                </div>
              ))}
            </div>
          ) : conditions.length === 0 ? (
            <p className="py-6 text-center text-[13px] italic text-slate-400 dark:text-slate-500">
              {t("patientProfile.noConditions")}
            </p>
          ) : (
            <div className="space-y-2">
              {conditions.map((c) => (
                <div
                  key={c.id}
                  className="group flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-800/50"
                >
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-slate-800 dark:text-slate-200">
                      {c.name}
                    </div>
                    {c.notes && (
                      <div className="mt-0.5 text-[11.5px] text-slate-500 dark:text-slate-400">
                        {c.notes}
                      </div>
                    )}
                    <div className="mono mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
                      {c.severity && `${c.severity} · `}
                      {t("patientProfile.recorded")} {formatDate(c.createdAt)}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => setConditionModal({ existing: c })}
                      className="rounded p-1.5 text-slate-400 hover:bg-white hover:text-brand-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-brand-400"
                      aria-label={t("patientProfile.editCondition")}
                    >
                      <EditIcon width={14} height={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemoveCondition(c)}
                      disabled={removingConditionId === c.id}
                      className="rounded p-1.5 text-slate-400 hover:bg-white hover:text-red-600 disabled:opacity-40 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-red-400"
                      aria-label={t("patientProfile.removeCondition")}
                    >
                      <TrashIcon width={14} height={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ── MEDICATION HISTORY ── */}
      <div className="mt-6 mb-4">
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-[15px] font-bold text-slate-900 dark:text-slate-100">
              {t("patientProfile.historyTitle")}
            </h2>
            {rxHistory && rxHistory.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    ["all", t("patientProfile.filterAll")],
                    ["last90", t("patientProfile.filterLast90")],
                    ["lastYear", t("patientProfile.filterLastYear")],
                    ["byDrug", t("patientProfile.filterByDrug")],
                  ] as [FilterKey, string][]
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setHistoryFilter(key)}
                    className={`rounded-full px-3 py-1 text-[12px] font-medium transition-colors ${
                      historyFilter === key
                        ? "bg-brand-600 text-white"
                        : "border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {rxError ? (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12.5px] text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              {rxError}
            </div>
          ) : rxHistory === null ? (
            <div className="space-y-4">
              {[0, 1].map((i) => (
                <div key={i}>
                  <Skl w="20%" h={11} />
                  <Skl w="60%" h={14} mt={6} />
                </div>
              ))}
            </div>
          ) : rxHistory.length === 0 ? (
            <p className="py-8 text-center text-[13px] italic text-slate-400 dark:text-slate-500">
              {t("patientProfile.noHistory")}
            </p>
          ) : (
            <div className="relative">
              <span className="absolute bottom-2 left-[10px] top-2 w-px bg-slate-200 dark:bg-slate-800" />
              {filteredHistory.map((r, i) => (
                <HistoryRow key={r.rxId} row={r} index={i} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
