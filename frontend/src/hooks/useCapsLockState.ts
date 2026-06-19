import { useEffect, useState, type RefObject } from "react";

/**
 * Live Caps Lock state for the element behind `ref`.
 *
 * Detection is event-driven: we read `KeyboardEvent.getModifierState("CapsLock")`
 * on keydown and keyup. There is no browser API to *query* the lock state
 * outside of a keyboard event, so we never poll.
 *
 * The two readings are treated **asymmetrically**, to stay robust against
 * handheld barcode scanners. A wedge scanner emits its payload as a rapid
 * keystroke burst and — crucially — reports `CapsLock=OFF` on those synthetic
 * events even when the lock is physically engaged (it sends correct-case
 * characters regardless of the host lock). A naive "read the latest event"
 * detector therefore lets a scan silently dismiss the warning. So:
 *
 *   - ANY event reporting `CapsLock=ON` turns the warning on — the lock is
 *     unambiguously engaged, whoever the keystroke came from.
 *   - Only the **physical Caps Lock key** (`event.key === "CapsLock"`) is
 *     allowed to turn it back off. A regular key reporting OFF (e.g. a scanner
 *     burst) is ignored, so a scan can never clear the warning while Caps Lock
 *     is still down. This is the HMVO scan-integrity requirement: the submit
 *     stays blocked until the user physically releases Caps Lock.
 *
 * Consequence: once engaged, the warning clears only when the user toggles
 * Caps Lock off while the field is focused. Erring toward "still on" is the
 * safe side for an HMVS submit gate.
 *
 * Caveat: the state can only refresh once a key is pressed while the field is
 * focused. If the user toggles Caps Lock with the field blurred, the warning
 * surfaces on their next keystroke — which is exactly when it matters.
 */
export function useCapsLockState(ref: RefObject<HTMLElement>): boolean {
  const [capsLockOn, setCapsLockOn] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const sync = (event: KeyboardEvent) => {
      const on = event.getModifierState("CapsLock");
      if (event.key === "CapsLock") {
        // Physical toggle of the lock key — authoritative in both directions.
        setCapsLockOn(on);
      } else if (on) {
        // Any other key reporting the lock engaged turns the warning on.
        setCapsLockOn(true);
      }
      // A non-CapsLock key reporting "off" is deliberately ignored: it may be a
      // wedge scanner whose burst doesn't carry the host Caps Lock state, and we
      // must not let a scan dismiss an active warning.
    };

    el.addEventListener("keydown", sync);
    el.addEventListener("keyup", sync);
    return () => {
      el.removeEventListener("keydown", sync);
      el.removeEventListener("keyup", sync);
    };
    // `ref` is a RefObject — stable for the element's lifetime — so this is
    // effectively a `[]` effect: bind once on mount, unbind on unmount. (If this
    // hook is ever reused where the element is conditionally rendered, the
    // `if (!el) return` guard above would need a retry path.)
  }, [ref]);

  return capsLockOn;
}
