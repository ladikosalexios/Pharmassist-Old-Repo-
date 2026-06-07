import { useEffect, useState, type RefObject } from "react";

/**
 * Live Caps Lock state for the element behind `ref`.
 *
 * Detection is strictly event-driven: we read
 * `KeyboardEvent.getModifierState("CapsLock")` on keydown and keyup. There is no
 * browser API to *query* the lock state outside of a keyboard event, so we never
 * poll — polling would burn cycles and still only ever be as fresh as the last
 * keystroke. Listeners are bound to the passed element (not `window`), so the
 * hook reports solely on the field that owns the ref and never reacts to typing
 * in other inputs.
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
      setCapsLockOn(event.getModifierState("CapsLock"));
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
