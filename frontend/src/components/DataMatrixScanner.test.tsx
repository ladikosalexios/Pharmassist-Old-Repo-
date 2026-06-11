import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import i18n from "../lib/i18n";
import { DataMatrixScanner, type ScanEntryMode } from "./DataMatrixScanner";

// Mock ZXing reader to avoid hardware/WASM issues in jsdom.
vi.mock("@zxing/browser", () => {
  return {
    BrowserMultiFormatReader: class {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      decodeFromVideoDevice = vi.fn().mockImplementation((_id: any, _el: any, callback: any) => {
        // Expose a way for tests to trigger a decode result.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).__triggerScan = (text: string) =>
          callback({ getText: () => text }, null, { stop: vi.fn() });
        return Promise.resolve();
      });
    },
  };
});

beforeAll(async () => {
  await i18n.changeLanguage("el");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (window as any).__triggerScan;
});

function Harness({ onScan }: { onScan: (val: string, mode: ScanEntryMode) => void }) {
  return <DataMatrixScanner onScan={onScan} />;
}

describe("DataMatrixScanner", () => {
  it("classifies a fast wedge burst of a clean payload as non-manual", async () => {
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);
    const input = screen.getByPlaceholderText("]d20105700123456789...");

    let now = 1000;
    vi.spyOn(performance, "now").mockImplementation(() => now);

    // Fast burst: "123" + Enter, each 10ms apart (< 30ms).
    fireEvent.change(input, { target: { value: "1" } });
    fireEvent.keyDown(input, { key: "1" });
    now += 10;
    fireEvent.change(input, { target: { value: "12" } });
    fireEvent.keyDown(input, { key: "2" });
    now += 10;
    fireEvent.change(input, { target: { value: "123" } });
    fireEvent.keyDown(input, { key: "3" });
    now += 10;
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onScan).toHaveBeenCalledWith("123", "non-manual");
  });

  it("classifies slow hand-typed entry as manual", async () => {
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);
    const input = screen.getByPlaceholderText("]d20105700123456789...");

    let now = 1000;
    vi.spyOn(performance, "now").mockImplementation(() => now);

    // Slow typing: "123" + Enter, each 100ms apart (> 30ms).
    fireEvent.change(input, { target: { value: "1" } });
    fireEvent.keyDown(input, { key: "1" });
    now += 100;
    fireEvent.change(input, { target: { value: "12" } });
    fireEvent.keyDown(input, { key: "2" });
    now += 100;
    fireEvent.change(input, { target: { value: "123" } });
    fireEvent.keyDown(input, { key: "3" });
    now += 100;
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onScan).toHaveBeenCalledWith("123", "manual");
  });

  it("blocks submission if Caps Lock is detected at the moment of Enter", async () => {
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);
    const input = screen.getByPlaceholderText("]d20105700123456789...");

    fireEvent.change(input, { target: { value: "ABC" } });

    // Simulate Enter with Caps Lock state active on the event.
    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true });
    Object.defineProperty(event, "getModifierState", {
      value: (key: string) => key === "CapsLock",
    });
    fireEvent(input, event);

    expect(onScan).not.toHaveBeenCalled();
  });

  it("blocks non-ASCII (Greek) bursts synchronously at submit", async () => {
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);
    const input = screen.getByPlaceholderText("]d20105700123456789...");

    // Fast burst of Greek characters.
    fireEvent.change(input, { target: { value: "αβγ" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onScan).not.toHaveBeenCalled();
  });

  it("reports non-manual for the camera scanning path", async () => {
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);

    // Switch to camera mode.
    fireEvent.click(screen.getByText("Χρήση κάμερας"));

    // Trigger the mocked scan result.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__triggerScan("CAMERA_PAYLOAD");

    expect(onScan).toHaveBeenCalledWith("CAMERA_PAYLOAD", "non-manual");
  });
});
