import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ClipboardIcon,
  DownloadIcon,
  FileTextIcon,
  SearchIcon,
  FilterIcon,
  AlertCircleIcon,
  CheckCircleIcon,
} from "../components/Icons";
import { DocumentationDetailModal } from "../components/DocumentationDetailModal";
import { useToast } from "../components/Toast";
import {
  ApiError,
  exportDocumentation,
  exportDocumentationRecord,
  listDocumentation,
} from "../lib/api";
import type {
  DeliveryMethod,
  DeliveryMethodFilter,
  DocumentationListResponse,
  DocumentationRecord,
} from "../types";

const METHOD_OPTIONS: { value: DeliveryMethodFilter; label: string }[] = [
  { value: "ALL", label: "All Methods" },
  { value: "PRINT", label: "Print" },
  { value: "DIGITAL", label: "Digital" },
  { value: "BOTH", label: "Both" },
];

const METHOD_TONE: Record<DeliveryMethod, string> = {
  PRINT: "bg-blue-100 text-blue-800",
  DIGITAL: "bg-emerald-100 text-emerald-800",
  BOTH: "bg-violet-100 text-violet-800",
};

const METHOD_LABEL: Record<DeliveryMethod, string> = {
  PRINT: "Print",
  DIGITAL: "Digital",
  BOTH: "Print + Digital",
};

const SETTING_TONE: Record<DocumentationRecord["setting"], string> = {
  Private: "border-slate-200 bg-slate-100 text-slate-700",
  Hospital: "border-amber-200 bg-amber-100 text-amber-800",
};

export function Documentation() {
  const { toast } = useToast();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [method, setMethod] = useState<DeliveryMethodFilter>("ALL");
  const [data, setData] = useState<DocumentationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [exportingAll, setExportingAll] = useState(false);
  const [exportingId, setExportingId] = useState<string | null>(null);

  // Debounce the search input.
  useEffect(() => {
    const t = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listDocumentation({ q: query || undefined, method })
      .then((res) => {
        if (active) setData(res);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load documentation records.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, method]);

  const stats = data?.stats ?? { total: 0, print: 0, digital: 0, both: 0 };

  const statCards = useMemo(
    () => [
      {
        label: "Total Records",
        value: stats.total,
        tone: "bg-slate-100 text-slate-700",
        valueClass: "text-slate-900",
      },
      {
        label: "Print Delivery",
        value: stats.print,
        tone: "bg-blue-100 text-blue-700",
        valueClass: "text-blue-700",
      },
      {
        label: "Digital Delivery",
        value: stats.digital,
        tone: "bg-emerald-100 text-emerald-700",
        valueClass: "text-emerald-700",
      },
      {
        label: "Both Methods",
        value: stats.both,
        tone: "bg-violet-100 text-violet-700",
        valueClass: "text-violet-700",
      },
    ],
    [stats],
  );

  async function onExportAll() {
    setExportingAll(true);
    try {
      await exportDocumentation({ q: query || undefined, method });
      toast("Documentation log exported", "success");
    } catch (e) {
      toast(e instanceof ApiError ? `Export failed: ${e.message}` : "Export failed.", "error");
    } finally {
      setExportingAll(false);
    }
  }

  async function onExportRecord(id: string) {
    setExportingId(id);
    try {
      await exportDocumentationRecord(id);
      toast(`Exported ${id}`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? `Export failed: ${e.message}` : "Export failed.", "error");
    } finally {
      setExportingId(null);
    }
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-7 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Documentation &amp; Legal Log</h1>
          <p className="mt-1 text-sm text-slate-500">
            Record of patient counseling and medication dispensing
          </p>
        </div>
        <button
          type="button"
          onClick={onExportAll}
          disabled={exportingAll}
          className="btn btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {exportingAll ? <span className="spinner" /> : <DownloadIcon />}
          {exportingAll ? "Exporting…" : "Export Report"}
        </button>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map(({ label, value, tone, valueClass }) => (
          <div key={label} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-medium text-slate-500">{label}</div>
                <div className={`mt-1 text-3xl font-bold ${valueClass}`}>
                  {loading ? "—" : value}
                </div>
              </div>
              <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone}`}>
                <ClipboardIcon width={18} height={18} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Search + filter */}
      <div className="card mb-5 flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="relative flex-1 min-w-[220px]">
          <SearchIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by patient name or prescription code..."
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          />
        </div>
        <div className="relative">
          <FilterIcon
            width={16}
            height={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as DeliveryMethodFilter)}
            className="rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-8 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
            aria-label="Filter by delivery method"
          >
            {METHOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Records */}
      {error ? (
        <div className="card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div className="card flex items-center gap-2 px-4 py-6 text-sm text-slate-500">
          <span className="spinner text-brand-600" /> Loading records…
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="card px-4 py-10 text-center text-sm text-slate-500">
          No records match your filters.
        </div>
      ) : (
        <ul className="space-y-3">
          {data.items.map((rec) => (
            <li key={rec.id}>
              <RecordCard
                record={rec}
                exporting={exportingId === rec.id}
                onView={() => setDetailId(rec.id)}
                onExport={() => onExportRecord(rec.id)}
              />
            </li>
          ))}
        </ul>
      )}

      {/* Legal notice */}
      <div className="mt-8 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm text-blue-900">
        <div className="mb-1 flex items-center gap-2 font-semibold">
          <CheckCircleIcon width={16} height={16} className="text-blue-600" /> Legal Compliance
        </div>
        <p className="leading-relaxed">
          All documentation records are maintained in compliance with pharmacy regulations and HIPAA
          requirements. Records are retained for the legally required period and are accessible for
          audits and inspections. Each entry includes pharmacist signature, timestamp, and delivery
          confirmation.
        </p>
      </div>

      <DocumentationDetailModal
        open={detailId !== null}
        recordId={detailId}
        onClose={() => setDetailId(null)}
      />
    </div>
  );
}

interface RecordCardProps {
  record: DocumentationRecord;
  exporting: boolean;
  onView: () => void;
  onExport: () => void;
}

function RecordCard({ record, exporting, onView, onExport }: RecordCardProps) {
  return (
    <article className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900">{record.patientName}</h3>
            <span className="chip border border-brand-100 bg-brand-50 font-mono text-brand-700">
              {record.rxId}
            </span>
            <span className={`chip border ${SETTING_TONE[record.setting]}`}>{record.setting}</span>
            <span className={`chip ${METHOD_TONE[record.deliveryMethod]}`}>
              {METHOD_LABEL[record.deliveryMethod]}
            </span>
          </div>

          <Link
            to={`/prescription/${record.rxId}`}
            className="mt-1.5 inline-block text-sm font-medium text-brand-600 hover:underline"
          >
            {record.drugName}
          </Link>

          <div className="mt-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Information Provided
            </div>
            <p className="mt-1 text-sm leading-relaxed text-slate-700">
              {record.informationProvided}
            </p>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-1.5 text-[13px] text-slate-600 sm:grid-cols-2">
            <div>
              <span className="font-medium text-slate-500">Language:</span> {record.language}
            </div>
            <div>
              <span className="font-medium text-slate-500">Delivery Method:</span>{" "}
              {METHOD_LABEL[record.deliveryMethod]}
            </div>
            <div className="sm:col-span-2 mt-1 text-xs text-slate-500">
              Dispensed by:{" "}
              <span className="font-medium text-slate-700">PharmD {record.pharmacistName}</span> ·{" "}
              {formatTimestamp(record.dispensedAt)}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <button type="button" onClick={onView} className="btn btn-outline">
            <FileTextIcon /> View Details
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={exporting}
            className="btn btn-outline disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {exporting ? <span className="spinner" /> : <DownloadIcon />}
            {exporting ? "Exporting…" : "Export"}
          </button>
        </div>
      </div>
    </article>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
