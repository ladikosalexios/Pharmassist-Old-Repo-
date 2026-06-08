import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircleIcon, AlertTriangleIcon, AlertCircleIcon } from "./Icons";

export type ToastVariant = "success" | "warn" | "error" | "info";

export interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const TONE: Record<ToastVariant, { box: string; icon: ReactNode }> = {
  success: {
    box: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
    icon: (
      <CheckCircleIcon width={16} height={16} className="text-emerald-600 dark:text-emerald-400" />
    ),
  },
  warn: {
    box: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
    icon: (
      <AlertTriangleIcon width={16} height={16} className="text-amber-600 dark:text-amber-400" />
    ),
  },
  error: {
    box: "border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300",
    icon: <AlertCircleIcon width={16} height={16} className="text-red-600 dark:text-red-400" />,
  },
  info: {
    box: "border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200",
    icon: <CheckCircleIcon width={16} height={16} className="text-brand-600 dark:text-brand-400" />,
  },
};

const DURATION_MS = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  // Aliased: `t` is the per-toast loop variable in the render map below.
  const { t: tr } = useTranslation();
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, variant: ToastVariant = "success") => {
      const id = Date.now() + Math.random();
      setToasts((ts) => [...ts, { id, message, variant }]);
      setTimeout(() => dismiss(id), DURATION_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed right-4 top-4 z-[90] flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((t) => {
          const tone = TONE[t.variant];
          return (
            <div
              key={t.id}
              role="status"
              className={`pointer-events-auto flex items-start gap-2 rounded-lg border ${tone.box} px-3.5 py-2.5 text-sm shadow-cardLg animate-alert-in`}
            >
              <span className="mt-0.5 shrink-0">{tone.icon}</span>
              <div className="flex-1">{t.message}</div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="ml-1 -mr-1 rounded p-0.5 text-slate-500 hover:bg-black/5 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-100"
                aria-label={tr("common.dismiss")}
              >
                <svg
                  width={14}
                  height={14}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
