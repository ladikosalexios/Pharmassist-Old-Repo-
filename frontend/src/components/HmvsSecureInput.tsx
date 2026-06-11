import {
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  forwardRef,
  type KeyboardEventHandler,
  type RefObject,
} from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangleIcon } from "./Icons";
import { useCapsLockState } from "../hooks/useCapsLockState";
import { useNonLatinInputDetector } from "../hooks/useNonLatinInputDetector";

/**
 * Why a pending submit is blocked. `null` means the field is clean.
 * - "caps-lock"        Caps Lock is on
 * - "keyboard-layout"  a non-ASCII character is present, e.g. Greek (wrong OS layout)
 * - "both"             both conditions are true at once
 */
export type HmvsBlockReason = "caps-lock" | "keyboard-layout" | "both" | null;

/**
 * Handle exposed by HmvsSecureInput to allow parent components to perform
 * synchronous validation and check for wedge-scanner "burst" entry.
 */
export interface HmvsSecureInputHandle {
  /**
   * Re-validates Caps Lock and Layout synchronously against the current value.
   * Accepts an optional KeyboardEvent to read the modifier state directly,
   * bypassing the rendered state which might be stale during a rapid burst.
   */
  isClean: (event?: React.KeyboardEvent | KeyboardEvent) => boolean;
  /**
   * Returns true if the current value was entered as a rapid burst (e.g. from
   * a handheld wedge scanner). Reset whenever the field is cleared.
   */
  isBurst: () => boolean;
  /** Direct access to focus the underlying input. */
  focus: () => void;
}

export interface HmvsSecureInputProps {
  value: string;
  onChange: (value: string) => void;
  /**
   * Fired whenever the block reason changes — including once on mount with the
   * initial reason (`null`, or `"keyboard-layout"` if `value` starts non-ASCII).
   * Emits `null` once the field clears.
   */
  onBlock: (reason: HmvsBlockReason) => void;
  /** Optional visible label; omit when the surrounding UI already labels the field. */
  label?: string;
  /** Accessible name forwarded to the input — supply when `label` is omitted. */
  ariaLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  /** Render the value in a monospace font (for fixed-width codes like GS1). */
  mono?: boolean;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement>;
  /**
   * External ref to the underlying input — used both for parent-driven focus
   * and for Caps Lock detection. Falls back to an internal ref when omitted.
   */
  inputRef?: RefObject<HTMLInputElement>;
}

/**
 * A guarded text input for HMVS / FMD security codes, where a mistyped pack
 * identifier — Caps Lock left on, or the OS still in a Greek layout — silently
 * corrupts the scan. It surfaces both problems inline and tells the parent, via
 * `onBlock`, when the value must not be submitted.
 *
 * It deliberately does NOT block keystrokes: the field keeps accepting whatever
 * is typed (a half-entered value is never eaten). Only the *submit* is meant to
 * be gated, which the parent does by reacting to `onBlock`.
 *
 * Purpose-built for HMVS code entry — do not drop it onto ordinary fields. A
 * patient-name field, for instance, must accept Greek.
 */
export const HmvsSecureInput = forwardRef<HmvsSecureInputHandle, HmvsSecureInputProps>(
  (
    {
      value,
      onChange,
      onBlock,
      label,
      ariaLabel,
      placeholder,
      disabled,
      mono,
      onKeyDown,
      inputRef,
    },
    forwardedRef,
  ) => {
    const { t } = useTranslation();
    const internalInputRef = useRef<HTMLInputElement>(null);
    // Use the caller's inputRef when provided; otherwise keep our own.
    const inputElRef = inputRef ?? internalInputRef;

    const capsLockOn = useCapsLockState(inputElRef);
    const nonLatin = useNonLatinInputDetector(value);

    // Timing and synchronous state tracking for "burst" detection and race prevention.
    const lastKeyTimeRef = useRef<number>(0);
    const isBurstRef = useRef<boolean>(true);
    const lastCapsLockRef = useRef<boolean>(false);

    // Reset burst detection once the field is cleared.
    useEffect(() => {
      if (value === "") {
        isBurstRef.current = true;
        lastKeyTimeRef.current = 0;
      }
    }, [value]);

    useImperativeHandle(
      forwardedRef,
      () => ({
        isClean: (e) => {
          const caps = e ? e.getModifierState("CapsLock") : lastCapsLockRef.current;
          // eslint-disable-next-line no-control-regex
          const layoutBlocked = /[^\x00-\x7F]/.test(value);
          return !caps && !layoutBlocked;
        },
        isBurst: () => isBurstRef.current && value.length > 0,
        focus: () => inputElRef.current?.focus(),
      }),
      [value, inputElRef],
    );

    const reason: HmvsBlockReason =
      capsLockOn && nonLatin
        ? "both"
        : capsLockOn
          ? "caps-lock"
          : nonLatin
            ? "keyboard-layout"
            : null;
    const blocked = reason !== null;

    // Notify the parent only when the reason actually changes. `onBlock` is held
    // in a ref so an inline parent callback can't re-fire the effect every render.
    const onBlockRef = useRef(onBlock);
    useEffect(() => {
      onBlockRef.current = onBlock;
    });
    useEffect(() => {
      onBlockRef.current(reason);
    }, [reason]);

    const inputId = useId();
    const warningsId = `${inputId}-warnings`;

    return (
      <div>
        {label && (
          <label
            htmlFor={inputId}
            className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300"
          >
            {label}
          </label>
        )}
        <input
          id={inputId}
          ref={inputElRef}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            lastCapsLockRef.current = e.getModifierState("CapsLock");

            const now = performance.now();
            if (lastKeyTimeRef.current > 0) {
              const diff = now - lastKeyTimeRef.current;
              // Classify as manual if inter-key timing exceeds ~30ms.
              if (diff > 30) {
                isBurstRef.current = false;
              }
            }
            lastKeyTimeRef.current = now;

            onKeyDown?.(e);
          }}
          disabled={disabled}
          placeholder={placeholder}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          aria-label={label ? undefined : ariaLabel}
          aria-invalid={blocked}
          aria-describedby={blocked ? warningsId : undefined}
          className={[
            "w-full rounded-lg border bg-white px-3.5 py-2.5 text-[14px] text-slate-900 outline-none transition-colors",
            "placeholder:text-slate-400 disabled:opacity-60 dark:bg-slate-950 dark:text-slate-100",
            mono ? "mono placeholder:font-sans" : "",
            blocked
              ? "border-red-500 focus:border-red-500 focus:ring-2 focus:ring-red-100 dark:border-red-500/60 dark:focus:ring-red-500/20"
              : "border-slate-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-slate-700",
          ].join(" ")}
        />

        {blocked && (
          <div id={warningsId} role="alert" className="mt-1.5 space-y-1 animate-alert-in">
            {capsLockOn && (
              <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-red-700 dark:text-red-400">
                <AlertTriangleIcon width={14} height={14} className="shrink-0" />
                {t("hmvs.capsLockWarning")}
              </p>
            )}
            {nonLatin && (
              <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-red-700 dark:text-red-400">
                <AlertTriangleIcon width={14} height={14} className="shrink-0" />
                {t("hmvs.layoutWarning")}
              </p>
            )}
          </div>
        )}
      </div>
    );
  },
);

HmvsSecureInput.displayName = "HmvsSecureInput";
