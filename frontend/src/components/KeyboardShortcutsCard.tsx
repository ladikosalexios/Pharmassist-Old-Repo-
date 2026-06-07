import { useTranslation } from "react-i18next";

interface Shortcut {
  id: string;
  keys: string[];
}

const SHORTCUTS: Shortcut[] = [
  { id: "dashboard", keys: ["D"] },
  { id: "nextPending", keys: ["P"] },
  { id: "confirm", keys: ["C"] },
  { id: "flag", keys: ["F"] },
  { id: "closeModal", keys: ["Esc"] },
];

export function KeyboardShortcutsCard() {
  const { t } = useTranslation();
  return (
    <section className="card p-5">
      <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">
        {t("shortcuts.title")}
      </h2>
      <ul className="space-y-2">
        {SHORTCUTS.map((s) => (
          <li
            key={s.id}
            className="flex items-center justify-between gap-3 text-[13px] text-slate-700 dark:text-slate-300"
          >
            <span className="flex items-center gap-1">
              {s.keys.map((k) => (
                <Key key={k} label={k} />
              ))}
            </span>
            <span className="text-right text-slate-600 dark:text-slate-400">
              {t(`shortcuts.${s.id}`)}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">{t("shortcuts.note")}</p>
    </section>
  );
}

function Key({ label }: { label: string }) {
  return (
    <kbd className="inline-flex min-w-[24px] items-center justify-center rounded-md border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-700 shadow-[inset_0_-1px_0_rgba(15,23,42,0.08)] dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200">
      {label}
    </kbd>
  );
}
