import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

interface ModalRegistryValue {
  isOpen: boolean;
  push: () => void;
  pop: () => void;
}

const ModalRegistryContext = createContext<ModalRegistryValue | undefined>(undefined);

export function ModalRegistryProvider({ children }: { children: ReactNode }) {
  const [count, setCount] = useState(0);
  const push = useCallback(() => setCount((c) => c + 1), []);
  const pop = useCallback(() => setCount((c) => Math.max(0, c - 1)), []);
  const value = useMemo<ModalRegistryValue>(
    () => ({ isOpen: count > 0, push, pop }),
    [count, push, pop],
  );
  return <ModalRegistryContext.Provider value={value}>{children}</ModalRegistryContext.Provider>;
}

function useModalRegistry(): ModalRegistryValue {
  const ctx = useContext(ModalRegistryContext);
  if (!ctx)
    throw new Error("Modal registry context missing — wrap the app in <ModalRegistryProvider>");
  return ctx;
}

/**
 * Register a modal/drawer with the global registry while `open` is true.
 * The keyboard shortcuts hook suppresses non-Escape shortcuts whenever the
 * registry's count is non-zero.
 */
export function useModalRegistration(open: boolean): void {
  const { push, pop } = useModalRegistry();
  useEffect(() => {
    if (!open) return;
    push();
    return pop;
  }, [open, push, pop]);
}

export type ShortcutMap = Record<string, (event: KeyboardEvent) => void>;

interface UseKeyboardShortcutsOptions {
  /**
   * When `true`, shortcuts fire even if a modal is open. Default `false`.
   * Useful for keys that should always work (e.g. Escape).
   */
  bypassModalGuard?: boolean;
  /**
   * When `false`, this whole shortcut set is disabled. Default `true`.
   */
  enabled?: boolean;
}

/**
 * Register a set of keyboard shortcuts at the window level.
 *
 * - Keys are matched case-insensitively against `event.key`.
 * - Shortcuts are skipped when focus is inside an `<input>`, `<textarea>`,
 *   `<select>`, or any contentEditable element.
 * - Shortcuts are skipped when any modifier key (Cmd/Ctrl/Alt/Meta) is held,
 *   so Cmd+P (print) still works as expected.
 * - Shortcuts are skipped while a registered modal is open, unless
 *   `bypassModalGuard` is set.
 */
export function useKeyboardShortcuts(
  shortcuts: ShortcutMap,
  options: UseKeyboardShortcutsOptions = {},
): void {
  const { bypassModalGuard = false, enabled = true } = options;
  const { isOpen } = useModalRegistry();
  const shortcutsRef = useRef(shortcuts);
  // Always read the latest map so callers don't have to memoise it.
  shortcutsRef.current = shortcuts;

  useEffect(() => {
    if (!enabled) return;
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isInputTarget(event.target)) return;
      if (isOpen && !bypassModalGuard) return;
      const handler = shortcutsRef.current[event.key.toLowerCase()];
      if (!handler) return;
      event.preventDefault();
      handler(event);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, bypassModalGuard, isOpen]);
}

function isInputTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}
