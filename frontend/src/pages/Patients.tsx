import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  SearchIcon,
  XIcon,
  UsersIcon,
  AlertCircleIcon,
  RefreshIcon,
  ChevronRightIcon,
  AlertTriangleIcon,
} from "../components/Icons";
import { ApiError, getPatient, searchPatients } from "../lib/api";
import type { PatientProfile } from "../types";

type SearchState = "empty" | "searching" | "results" | "none" | "error" | "name-stub";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

const AV_TONES = [
  "bg-brand-100 text-brand-700",
  "bg-emerald-100 text-emerald-700",
  "bg-amber-100 text-amber-700",
  "bg-slate-200 text-slate-600",
];

function Skl({ w = "100%", h = 14, mt = 0 }: { w?: string; h?: number; mt?: number }) {
  return (
    <div className="sk animate-shimmer rounded" style={{ width: w, height: h, marginTop: mt }} />
  );
}

function SkRow({ i }: { i: number }) {
  return (
    <div
      className={`flex items-center gap-4 px-5 py-4 ${i > 0 ? "border-t border-slate-100" : ""}`}
    >
      <div className="sk animate-shimmer h-11 w-11 shrink-0 rounded-full" />
      <div className="flex-1">
        <Skl w="40%" h={14} />
        <Skl w="28%" h={12} mt={8} />
      </div>
      <Skl w="80px" h={12} />
    </div>
  );
}

function ResultRow({ p, index }: { p: PatientProfile; index: number }) {
  const { t } = useTranslation();
  const hasIntolerances = (p.intolerances?.length ?? 0) > 0;
  const amka = p.amka ?? p.id;
  return (
    <Link
      to={`/patients/${amka}`}
      className={`group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-slate-50 ${index > 0 ? "border-t border-slate-100" : ""}`}
    >
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[14px] font-bold ${AV_TONES[index % AV_TONES.length]}`}
      >
        {initials(p.name)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[14.5px] font-semibold text-slate-900">{p.name}</span>
          {hasIntolerances && (
            <span className="flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] font-semibold text-amber-700">
              <AlertTriangleIcon width={11} height={11} />
              {t("patients.intolerancesOnFile")}
            </span>
          )}
        </div>
        {amka && <div className="mono mt-0.5 text-[12.5px] text-slate-500">AMKA {amka}</div>}
      </div>
      {typeof p.age === "number" && (
        <div className="hidden w-24 shrink-0 text-[12.5px] text-slate-500 sm:block">
          {p.age} yrs{p.sex ? ` · ${p.sex}` : ""}
        </div>
      )}
      <span className="text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600">
        <ChevronRightIcon width={18} height={18} />
      </span>
    </Link>
  );
}

function isNumericQuery(q: string) {
  return /^\d+$/.test(q.trim());
}

export function Patients() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>("empty");
  const [results, setResults] = useState<PatientProfile[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function runSearch(q: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    abortRef.current?.abort();

    if (!q.trim()) {
      setState("empty");
      setResults([]);
      return;
    }

    setState("searching");

    debounceRef.current = setTimeout(async () => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      if (isNumericQuery(q)) {
        // AMKA / EKAA — direct lookup
        try {
          const patient = await getPatient(q.trim());
          if (ctrl.signal.aborted) return;
          setResults([patient]);
          setState("results");
        } catch (e) {
          if (ctrl.signal.aborted) return;
          if (e instanceof ApiError && e.status === 404) {
            setState("none");
          } else {
            setErrorMsg(e instanceof ApiError ? e.message : "Unexpected error.");
            setState("error");
          }
        }
      } else {
        // Name search — stub
        try {
          const patients = await searchPatients(q.trim());
          if (ctrl.signal.aborted) return;
          if (patients.length === 0) {
            setState("none");
          } else {
            setResults(patients);
            setState("results");
          }
        } catch (e) {
          if (ctrl.signal.aborted) return;
          if (e instanceof ApiError && e.status === 501) {
            setState("name-stub");
          } else {
            setErrorMsg(e instanceof ApiError ? e.message : "Unexpected error.");
            setState("error");
          }
        }
      }
    }, 400);
  }

  function handleInput(v: string) {
    setQuery(v);
    runSearch(v);
  }

  function handleRetry() {
    runSearch(query);
  }

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-8 lg:px-8">
      {/* header */}
      <div className="mb-6">
        <h1 className="text-[24px] font-bold tracking-tight text-slate-900">
          {t("patients.title")}
        </h1>
        <p className="mt-1 text-[13px] text-slate-500">{t("patients.subtitle")}</p>
      </div>

      {/* search input */}
      <div className="relative">
        <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
          <SearchIcon width={19} height={19} />
        </span>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          placeholder={t("patients.searchPlaceholder")}
          className="w-full rounded-xl border border-slate-200 bg-white py-3.5 pl-12 pr-10 text-[15px] text-slate-900 shadow-card outline-none transition-shadow placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
        {query && (
          <button
            type="button"
            onClick={() => handleInput("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-300 hover:bg-slate-100 hover:text-slate-500"
            aria-label="Clear search"
          >
            <XIcon width={16} height={16} />
          </button>
        )}
      </div>

      {/* results area */}
      <div className="mt-7">
        {state === "empty" && (
          <div className="flex animate-fade-in flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-16 text-center shadow-card">
            <div className="relative flex h-16 w-16 items-center justify-center">
              <span className="absolute -left-1 -top-1 flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-300">
                <UsersIcon width={20} height={20} />
              </span>
              <span className="absolute bottom-0 right-0 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-500">
                <SearchIcon width={22} height={22} />
              </span>
            </div>
            <h3 className="mt-5 text-[15px] font-bold text-slate-900">
              {t("patients.lookUpTitle")}
            </h3>
            <p className="mt-1.5 max-w-[340px] text-[13px] leading-relaxed text-slate-500">
              {t("patients.lookUpDesc")}
            </p>
          </div>
        )}

        {state === "searching" && (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
            {[0, 1, 2].map((i) => (
              <SkRow key={i} i={i} />
            ))}
          </div>
        )}

        {state === "results" && (
          <div className="animate-fade-in">
            <div className="mb-2.5 text-[12px] font-medium text-slate-400">
              {t("patients.count", { count: results.length })}
            </div>
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
              {results.map((p, i) => (
                <ResultRow key={p.amka ?? p.id} p={p} index={i} />
              ))}
            </div>
          </div>
        )}

        {state === "name-stub" && (
          <div className="animate-fade-in overflow-hidden rounded-xl border border-amber-200 bg-amber-50 px-5 py-5">
            <div className="flex items-start gap-3">
              <AlertCircleIcon width={18} height={18} className="mt-0.5 shrink-0 text-amber-600" />
              <p className="text-[13px] leading-relaxed text-amber-800">
                {t("patients.nameSearchNote")}
              </p>
            </div>
          </div>
        )}

        {state === "none" && (
          <div className="flex animate-fade-in flex-col items-center rounded-2xl border border-slate-200 bg-white px-6 py-14 text-center shadow-card">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
              <SearchIcon width={22} height={22} />
            </div>
            <h3 className="mt-4 text-[15px] font-bold text-slate-900">
              {t("patients.notFoundTitle")}
            </h3>
            <p className="mt-1.5 max-w-[360px] text-[13px] leading-relaxed text-slate-500">
              {t("patients.notFoundDesc")}
            </p>
          </div>
        )}

        {state === "error" && (
          <div className="flex animate-fade-in flex-col items-center rounded-2xl border border-red-200 bg-red-50 px-6 py-14 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600">
              <AlertCircleIcon width={24} height={24} />
            </div>
            <h3 className="mt-4 text-[15px] font-bold text-red-800">{t("patients.errorTitle")}</h3>
            <p className="mt-1.5 max-w-[360px] text-[13px] leading-relaxed text-red-700/90">
              {errorMsg ?? t("patients.errorDesc")}
            </p>
            <button
              type="button"
              onClick={handleRetry}
              className="mt-4 flex items-center gap-1.5 rounded-lg border border-red-300 bg-white px-4 py-2 text-[13px] font-semibold text-red-700 transition-colors hover:bg-red-50"
            >
              <RefreshIcon width={15} height={15} /> {t("patients.retry")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
