interface Shortcut {
  keys: string[];
  description: string;
}

const SHORTCUTS: Shortcut[] = [
  { keys: ["D"],      description: "Go to dashboard" },
  { keys: ["P"],      description: "Open next pending prescription" },
  { keys: ["C"],      description: "Confirm approval (on a prescription)" },
  { keys: ["F"],      description: "Flag discrepancy (on a prescription)" },
  { keys: ["Esc"],    description: "Close any open modal or drawer" },
];

export function KeyboardShortcutsCard() {
  return (
    <section className="card p-5">
      <h2 className="mb-3 text-base font-semibold text-slate-900">Keyboard Shortcuts</h2>
      <ul className="space-y-2">
        {SHORTCUTS.map((s) => (
          <li key={s.description} className="flex items-center justify-between gap-3 text-[13px] text-slate-700">
            <span className="flex items-center gap-1">
              {s.keys.map((k) => <Key key={k} label={k} />)}
            </span>
            <span className="text-right text-slate-600">{s.description}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-slate-500">
        Shortcuts pause while an input is focused or a dialog is open.
      </p>
    </section>
  );
}

function Key({ label }: { label: string }) {
  return (
    <kbd className="inline-flex min-w-[24px] items-center justify-center rounded-md border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-700 shadow-[inset_0_-1px_0_rgba(15,23,42,0.08)]">
      {label}
    </kbd>
  );
}
