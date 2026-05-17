import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangleIcon, SearchIcon, FilterIcon, AlertCircleIcon } from "../../components/Icons";
import { useToast } from "../../components/Toast";
import { ApiError } from "../../lib/api";
import {
  createSafetyRule,
  listSafetyRules,
  updateSafetyRule,
  type SafetyRule,
  type SafetyRuleCreate,
} from "../../lib/adminApi";

interface FormState {
  rule_code: string;
  check_type: string;
  severity: string;
  message_en: string;
  trigger_atc: string;
  trigger_condition_code: string;
  conflicting_atc: string;
  details_en: string;
  recommended_action_en: string;
}

const EMPTY: FormState = {
  rule_code: "",
  check_type: "",
  severity: "",
  message_en: "",
  trigger_atc: "",
  trigger_condition_code: "",
  conflicting_atc: "",
  details_en: "",
  recommended_action_en: "",
};

const TEXT_FIELDS: { key: keyof FormState; label: string; required?: boolean }[] = [
  { key: "rule_code", label: "Rule code", required: true },
  { key: "check_type", label: "Check type", required: true },
  { key: "severity", label: "Severity", required: true },
  { key: "trigger_atc", label: "Trigger ATC" },
  { key: "trigger_condition_code", label: "Trigger condition code" },
  { key: "conflicting_atc", label: "Conflicting ATC" },
];

const TEXTAREA_FIELDS: { key: keyof FormState; label: string; required?: boolean }[] = [
  { key: "message_en", label: "Message", required: true },
  { key: "details_en", label: "Details" },
  { key: "recommended_action_en", label: "Recommended action" },
];

function toForm(r: SafetyRule): FormState {
  return {
    rule_code: r.rule_code,
    check_type: r.check_type,
    severity: r.severity,
    message_en: r.message_en,
    trigger_atc: r.trigger_atc ?? "",
    trigger_condition_code: r.trigger_condition_code ?? "",
    conflicting_atc: r.conflicting_atc ?? "",
    details_en: r.details_en ?? "",
    recommended_action_en: r.recommended_action_en ?? "",
  };
}

function severityTone(severity: string): string {
  const s = severity.toUpperCase();
  if (s === "MAJOR" || s === "CONTRAINDICATION") return "bg-red-100 text-red-800";
  if (s === "MODERATE") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-600";
}

export function AdminSafetyRules() {
  const { toast } = useToast();
  const [items, setItems] = useState<SafetyRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<SafetyRule | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  function reload() {
    setLoading(true);
    setError(null);
    listSafetyRules({
      q: query || undefined,
      active: activeFilter === "" ? undefined : activeFilter === "true",
      limit: 200,
    })
      .then((res) => setItems(res.items))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load safety rules."),
      )
      .finally(() => setLoading(false));
  }

  useEffect(reload, [query, activeFilter]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormErr(null);
    setShowForm(true);
  }

  function openEdit(r: SafetyRule) {
    setEditing(r);
    setForm(toForm(r));
    setFormErr(null);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormErr(null);
    if (
      !form.rule_code.trim() ||
      !form.check_type.trim() ||
      !form.severity.trim() ||
      !form.message_en.trim()
    ) {
      setFormErr("Rule code, check type, severity and message are required.");
      return;
    }
    const payload: SafetyRuleCreate = {
      rule_code: form.rule_code.trim(),
      check_type: form.check_type.trim(),
      severity: form.severity.trim(),
      message_en: form.message_en.trim(),
      trigger_atc: form.trigger_atc.trim() || null,
      trigger_condition_code: form.trigger_condition_code.trim() || null,
      conflicting_atc: form.conflicting_atc.trim() || null,
      details_en: form.details_en.trim() || null,
      recommended_action_en: form.recommended_action_en.trim() || null,
    };
    setSubmitting(true);
    try {
      if (editing) {
        await updateSafetyRule(editing.id, payload);
        toast("Safety rule updated", "success");
      } else {
        await createSafetyRule(payload);
        toast("Safety rule created", "success");
      }
      closeForm();
      reload();
    } catch (e) {
      setFormErr(e instanceof ApiError ? e.message : "Could not save the safety rule.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onToggle(r: SafetyRule) {
    setTogglingId(r.id);
    try {
      await updateSafetyRule(r.id, { active: !r.active });
      toast(r.active ? "Safety rule deactivated" : "Safety rule activated", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not update the safety rule.", "error");
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Safety Rules</h1>
          <p className="mt-1 text-sm text-slate-500">
            Clinical safety rules that drive the prescription safety checks.
          </p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="btn bg-slate-900 text-white hover:bg-slate-800"
        >
          <AlertTriangleIcon /> New Rule
        </button>
      </div>

      {showForm && (
        <form onSubmit={onSubmit} className="card mb-5 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">
            {editing ? `Edit ${editing.rule_code}` : "Create safety rule"}
          </h2>
          {formErr && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">
              <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
              <span>{formErr}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {TEXT_FIELDS.map(({ key, label, required }) => (
              <div key={key}>
                <label
                  htmlFor={`sr-${key}`}
                  className="mb-1.5 block text-[13px] font-medium text-slate-600"
                >
                  {label}
                  {required && <span className="text-red-500"> *</span>}
                </label>
                <input
                  id={`sr-${key}`}
                  type="text"
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
                />
              </div>
            ))}
            {TEXTAREA_FIELDS.map(({ key, label, required }) => (
              <div key={key} className="sm:col-span-2">
                <label
                  htmlFor={`sr-${key}`}
                  className="mb-1.5 block text-[13px] font-medium text-slate-600"
                >
                  {label}
                  {required && <span className="text-red-500"> *</span>}
                </label>
                <textarea
                  id={`sr-${key}`}
                  rows={3}
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full resize-y rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
                />
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn bg-slate-900 text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? <span className="spinner" /> : null}
              {submitting ? "Saving…" : editing ? "Save changes" : "Create safety rule"}
            </button>
            <button type="button" onClick={closeForm} className="btn btn-outline">
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="card mb-5 flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="relative min-w-[220px] flex-1">
          <SearchIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by rule code or message..."
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
        </div>
        <div className="relative">
          <FilterIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <select
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value)}
            aria-label="Filter by status"
            className="rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-8 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </div>

      {error ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-slate-900" /> Loading safety rules…
        </div>
      ) : items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No safety rules match your filters.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Rule code</th>
                <th className="px-4 py-3">Check type</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Message</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-mono text-slate-900">{r.rule_code}</td>
                  <td className="px-4 py-3 text-slate-700">{r.check_type}</td>
                  <td className="px-4 py-3">
                    <span className={`chip ${severityTone(r.severity)}`}>
                      {r.severity.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    <div className="max-w-md truncate">{r.message_en}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`chip ${
                        r.active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {r.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => openEdit(r)} className="btn btn-outline">
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onToggle(r)}
                        disabled={togglingId === r.id}
                        className="btn btn-outline disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {togglingId === r.id ? <span className="spinner" /> : null}
                        {r.active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
