import { useState } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import i18n from "../lib/i18n";
import { HmvsSecureInput, type HmvsBlockReason } from "./HmvsSecureInput";

const CAPS_WARNING = "Απενεργοποιήστε το Caps Lock πριν συνεχίσετε";
const LAYOUT_WARNING = "Αλλάξτε τη γλώσσα πληκτρολογίου σε αγγλικά πριν συνεχίσετε";
const LABEL = "HMVS pack code";

beforeAll(async () => {
  // Warnings are asserted in Greek, so pin the shared i18n instance to `el`
  // (this also proves the hmvs.* keys actually resolve in el.json).
  await i18n.changeLanguage("el");
});

afterEach(cleanup);

/** Controlled wrapper so typing genuinely re-renders the field, like a real form. */
function Harness({
  onBlock,
  initialValue = "",
}: {
  onBlock: (reason: HmvsBlockReason) => void;
  initialValue?: string;
}) {
  const [value, setValue] = useState(initialValue);
  return (
    <HmvsSecureInput
      label={LABEL}
      placeholder="Scan or type the pack code"
      value={value}
      onChange={setValue}
      onBlock={onBlock}
    />
  );
}

/**
 * Dispatch a real keydown whose getModifierState reports the given Caps state.
 * jsdom can't toggle the lock itself, so we override the method on the event —
 * this is exactly what the hook reads.
 */
function pressKeyWithCaps(input: HTMLElement, capsOn: boolean) {
  const event = new KeyboardEvent("keydown", { key: "a", bubbles: true });
  Object.defineProperty(event, "getModifierState", {
    configurable: true,
    value: (key: string) => key === "CapsLock" && capsOn,
  });
  fireEvent(input, event);
}

describe("HmvsSecureInput", () => {
  it("resolves the hmvs.* keys to the required Greek copy", () => {
    // The constants below pin the exact spec'd wording; this also proves the
    // keys exist in el.json. If the locale drifts, it fails loudly here rather
    // than as a vague text-not-found error in the rendering tests.
    expect(i18n.t("hmvs.capsLockWarning")).toBe(CAPS_WARNING);
    expect(i18n.t("hmvs.layoutWarning")).toBe(LAYOUT_WARNING);
  });

  it("blocks and warns when Caps Lock is on", () => {
    const onBlock = vi.fn();
    render(<Harness onBlock={onBlock} />);
    const input = screen.getByLabelText(LABEL);

    pressKeyWithCaps(input, true);

    expect(screen.getByText(CAPS_WARNING)).toBeTruthy();
    expect(screen.queryByText(LAYOUT_WARNING)).toBeNull();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(onBlock).toHaveBeenLastCalledWith("caps-lock");
  });

  it("blocks and warns on non-Latin (Greek) input while still accepting it", () => {
    const onBlock = vi.fn();
    render(<Harness onBlock={onBlock} />);
    const input = screen.getByLabelText(LABEL) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "Παρακετα" } });

    // The field still holds exactly what was typed — only submit is gated.
    expect(input.value).toBe("Παρακετα");
    expect(screen.getByText(LAYOUT_WARNING)).toBeTruthy();
    expect(screen.queryByText(CAPS_WARNING)).toBeNull();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(onBlock).toHaveBeenLastCalledWith("keyboard-layout");
  });

  it("stacks both warnings and emits 'both' when Caps Lock and Greek combine", () => {
    const onBlock = vi.fn();
    render(<Harness onBlock={onBlock} />);
    const input = screen.getByLabelText(LABEL);

    fireEvent.change(input, { target: { value: "Παρα" } });
    pressKeyWithCaps(input, true);

    expect(screen.getByText(CAPS_WARNING)).toBeTruthy();
    expect(screen.getByText(LAYOUT_WARNING)).toBeTruthy();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(onBlock).toHaveBeenLastCalledWith("both");
  });

  it("clears warnings and reports null once both conditions resolve", () => {
    const onBlock = vi.fn();
    render(<Harness onBlock={onBlock} initialValue="Παρα" />);
    const input = screen.getByLabelText(LABEL) as HTMLInputElement;

    pressKeyWithCaps(input, true);
    expect(onBlock).toHaveBeenLastCalledWith("both");

    // Caps Lock released — only the layout warning remains.
    pressKeyWithCaps(input, false);
    expect(screen.queryByText(CAPS_WARNING)).toBeNull();
    expect(onBlock).toHaveBeenLastCalledWith("keyboard-layout");

    // Field emptied — fully clean again.
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.queryByText(LAYOUT_WARNING)).toBeNull();
    expect(input.getAttribute("aria-invalid")).toBe("false");
    expect(onBlock).toHaveBeenLastCalledWith(null);
  });
});
