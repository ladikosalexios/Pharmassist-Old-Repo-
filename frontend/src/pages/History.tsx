import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  SearchIcon,
  CalendarIcon,
  DownloadIcon,
  PrinterIcon,
  SearchXIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  AlertCircleIcon,
} from "../components/Icons";
import { ApiError, exportDocumentation, listDocumentation } from "../lib/api";
import { useToast } from "../components/Toast";
import { DocumentationDetailModal } from "../components/DocumentationDetailModal";
import type { DeliveryMethod, DeliveryMethodFilter, DocumentationListResponse } from "../types";

const METHOD_TONE: Record<DeliveryMethod, string> = {
  PRINT: "bg-slate-100 text-slate-600",
  DIGITAL: "bg-brand-50 text-brand-700",
  BOTH: "bg-slate-100 text-slate-600",
};

const STATUS_TONE: Record<string, string> = {
  COMPLETED: "bg-emerald-50 text-emerald-700",
  FLAGGED: "bg-red-50 text-red-700",
  PENDING: "bg-amber-50 text-amber-700",
};

function Skl({ w = "100%", h = 12 }: { w?: string; h?: number }) {
  return <div className="sk animate-shimmer rounded" style={{ width: w, height: h }} />;
}

export function History() {
  const { t } = useTranslation();
  const { toast } = useToast();

  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [method, setMethod] = useState<DeliveryMethodFilter>("ALL");
  const [data, setData] = useState<DocumentationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search input → query state
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchInput]);

  // Fetch whenever query or method changes
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listDocumentation({ q: query || undefined, method })
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load history.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, method]);

  async function handleExport() {
    setExporting(true);
    try {
      await exportDocumentation({ q: query || undefined, method, format: "csv" });
    } catch {
      toast("Export failed. Please try again.", "error");
    } finally {
      setExporting(false);
    }
  }

  function resetFilters() {
    setSearchInput("");
    setQuery("");
    setMethod("ALL");
  }

  const stats = useMemo(() => {
    const s = data?.stats;
    return {
      today: s ? (s.print + s.digital + s.both).toString() : "—",
      total: data?.total ?? 0,
    };
  }, [data]);

  const methodFilters: { value: DeliveryMethodFilter; key: string }[] = [
    { value: "ALL", key: "methodAll" },
    { value: "PRINT", key: "methodPrint" },
    { value: "DIGITAL", key: "methodDigital" },
    { value: "BOTH", key: "methodBoth" },
  ];

  const isEmpty = !loading && !error && data?.items.length === 0;

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-8 lg:px-8">
      <DocumentationDetailModal
        open={detailId !== null}
        recordId={detailId}
        onClose={() => setDetailId(null)}
      />

      {/* header */}
      <div className="mb-6">
        <h1 className="text-[24px] font-bold tracking-tight text-slate-900">
          {t("history.title")}
        </h1>
        <p className="mt-1 text-[13px] text-slate-500">{t("history.subtitle")}</p>
      </div>

      {/* stats strip */}
      <div className="mb-5 flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl border border-slate-200 bg-white px-6 py-4 shadow-card">
        {[
          {
            label: t("history.statToday"),
            value: data?.stats ? data.stats.print + data.stats.digital + data.stats.both : "—",
          },
          { label: t("history.statMonth"), value: stats.total || "—" },
        ].map(({ label, value }, i) => (
          <div key={i} className="flex items-baseline gap-2">
            <span className="text-[20px] font-bold tabular-nums text-slate-900">{value}</span>
            <span className="text-[12px] font-medium text-slate-500">{label}</span>
          </div>
        ))}
      </div>

      {/* sticky filter bar */}
      <div className="sticky top-0 z-20 -mx-2 mb-4 rounded-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-card backdrop-blur">
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12.5px] font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            <CalendarIcon width={15} height={15} className="text-slate-400" />
            {t("history.dateRange")}
          </button>

          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            {methodFilters.map(({ value, key }) => (
              <button
                key={value}
                type="button"
                onClick={() => setMethod(value)}
                className={`rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                  method === value
                    ? "bg-white text-brand-700 shadow-card"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {t(`history.${key}`)}
              </button>
            ))}
          </div>

          <div className="relative min-w-[200px] flex-1">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <SearchIcon width={16} height={16} />
            </span>
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t("history.searchPlaceholder")}
              className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-[13px] text-slate-900 outline-none placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            />
          </div>

          <button
            type="button"
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12.5px] font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
          >
            <DownloadIcon width={15} height={15} />
            {t("history.exportCsv")}
          </button>
        </div>
      </div>

      {/* error */}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {/* loading skeletons */}
      {loading && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className={`flex items-center gap-4 px-5 py-3.5 ${i > 0 ? "border-t border-slate-100" : ""}`}
            >
              <Skl w="96px" />
              <Skl w="112px" />
              <Skl w="100%" />
              <Skl w="80px" h={20} />
            </div>
          ))}
        </div>
      )}

      {/* empty state */}
      {isEmpty && (
        <div className="flex animate-fade-in flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-16 text-center shadow-card">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
            <SearchXIcon width={22} height={22} />
          </div>
          <h3 className="mt-4 text-[15px] font-bold text-slate-900">{t("history.emptyTitle")}</h3>
          <p className="mt-1.5 max-w-[340px] text-[13px] text-slate-500">
            {t("history.emptyDesc")}
          </p>
          <button
            type="button"
            onClick={resetFilters}
            className="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-brand-600 transition-colors hover:bg-brand-50"
          >
            {t("history.resetFilters")}
          </button>
        </div>
      )}

      {/* results table */}
      {!loading && !isEmpty && data && (
        <div className="animate-fade-in overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
          {/* header row */}
          <div className="grid grid-cols-[140px_130px_1fr_1fr_90px_110px] items-center gap-4 border-b border-slate-200 bg-slate-50 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            <span>{t("history.colDateTime")}</span>
            <span>{t("history.colBarcode")}</span>
            <span>{t("history.colPatient")}</span>
            <span>{t("history.colMedication")}</span>
            <span>{t("history.colMethod")}</span>
            <span>{t("history.colStatus")}</span>
          </div>

          {data.items.map((r, i) => (
            <div
              key={r.id}
              className={`group relative grid grid-cols-[140px_130px_1fr_1fr_90px_110px] items-center gap-4 px-5 py-3.5 transition-colors hover:bg-slate-50 ${
                i > 0 ? "border-t border-slate-100" : ""
              }`}
            >
              <span className="mono text-[12px] text-slate-500">{r.dispensedAt}</span>
              <span className="mono truncate text-[12.5px] text-slate-600">{r.rxId}</span>
              <span className="truncate text-[13px] font-medium text-slate-900">
                {r.patientName}
              </span>
              <span className="truncate text-[12.5px] text-slate-600">{r.drugName}</span>
              <span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${METHOD_TONE[r.deliveryMethod]}`}
                >
                  {r.deliveryMethod}
                </span>
              </span>
              <span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${STATUS_TONE["COMPLETED"]}`}
                >
                  Dispensed
                </span>
              </span>

              {/* hover actions */}
              <div className="absolute right-4 top-1/2 flex -translate-y-1/2 items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  type="button"
                  className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11.5px] font-semibold text-slate-600 shadow-card hover:bg-slate-50"
                >
                  <PrinterIcon width={13} height={13} /> {t("history.print")}
                </button>
                <button
                  type="button"
                  onClick={() => setDetailId(r.id)}
                  className="flex items-center gap-1 rounded-lg bg-brand-600 px-2 py-1 text-[11.5px] font-semibold text-white shadow-card hover:bg-brand-700"
                >
                  {t("history.open")} <ChevronRightIcon width={13} height={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* pagination */}
      {!loading && !isEmpty && data && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-[12.5px] text-slate-500">
            {t("history.showingOf", { from: 1, to: data.items.length, total: data.total })}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400"
            >
              <ChevronLeftIcon width={16} height={16} />
            </button>
            <button
              type="button"
              className="flex h-8 min-w-8 items-center justify-center rounded-lg bg-brand-600 px-2 text-[13px] font-medium text-white"
            >
              1
            </button>
            <button
              type="button"
              disabled
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400"
            >
              <ChevronRightIcon width={16} height={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
