import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { YellowCards } from "./YellowCards";
import { emptyReport } from "../lib/yellowCards";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { name: "Test", email: "demo@example.com" } }),
}));
vi.mock("../components/YellowPdf", () => ({ YellowPdf: () => <div>PDF preview</div> }));
vi.mock("../components/YellowSignature", () => ({
  YellowSignature: () => <div>Saved signature</div>,
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const submission = {
  id: "send",
  preview_id: "preview",
  status: "QUEUED",
  approved_at: "2026-10-07T13:26:18Z",
  failure_code: null,
};
function setup() {
  let status = "QUEUED",
    submitted = false,
    pollingFails = false;
  const post = vi.fn(async () => new Response(JSON.stringify(submission), { status: 202 }));
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    if (input === "/yellow-cards/submissions") {
      if (init?.method === "POST") {
        submitted = true;
        return post();
      }
      if (pollingFails) throw new TypeError("Network error");
      return Response.json(submitted ? [{ ...submission, status }] : []);
    }
    if (input === "/yellow-cards/signature")
      return Response.json({ id: "signature", sha256: "hash" });
    if (input.endsWith("/previews"))
      return Response.json({
        id: "preview",
        revision: 1,
        signature_id: "signature",
        sha256: "hash",
        envelope: {
          from: "from.test",
          to: "to.test",
          reply_to: "reply.test",
          subject: "Test",
          body: "Test",
        },
      });
    return Response.json(
      init?.method === "POST"
        ? { id: "draft", revision: 1, data: emptyReport("Test", "demo@example.com") }
        : [],
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(
    <MemoryRouter>
      <YellowCards />
    </MemoryRouter>,
  );
  return {
    post,
    fetch,
    setStatus: (value: string) => {
      status = value;
    },
    failPolling: (value: boolean) => {
      pollingFails = value;
    },
  };
}
async function prepare() {
  await waitFor(() =>
    expect(
      (
        screen.getByRole("checkbox", {
          name: "Χρήση της αποθηκευμένης υπογραφής μου σε αυτή την αναφορά.",
        }) as HTMLInputElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Χρησιμοποιώ μόνο συνθετικά στοιχεία σε αυτή τη δοκιμή.",
    }),
  );
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Χρήση της αποθηκευμένης υπογραφής μου σε αυτή την αναφορά.",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Δημιουργία και προεπισκόπηση PDF" }));
  await screen.findByText("PDF preview");
  fireEvent.click(screen.getByRole("checkbox", { name: /Έλεγξα το PDF/ }));
}
const newReport = () => screen.getByRole("button", { name: "Νέα αναφορά" }) as HTMLButtonElement;

describe("Yellow Card submission recovery", () => {
  it("unlocks editing after a definite rejection", async () => {
    const api = setup();
    api.post.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Η αναφορά άλλαξε" }), { status: 409 }),
    );
    await prepare();
    fireEvent.click(screen.getByRole("button", { name: "Αποστολή στο τοπικό inbox" }));
    await screen.findByText("Η αναφορά άλλαξε");
    expect(newReport().disabled).toBe(false);
    expect(
      (screen.getByRole("combobox", { name: "Αποθηκευμένα προσχέδια" }) as HTMLSelectElement)
        .disabled,
    ).toBe(false);
    expect(screen.queryByText(/Η απάντηση της αποστολής εκκρεμεί/)).toBeNull();
  });

  it("keeps edits locked and reuses the same key after a lost response", async () => {
    const api = setup();
    api.post.mockRejectedValueOnce(new TypeError("Lost response"));
    await prepare();
    fireEvent.click(screen.getByRole("button", { name: "Αποστολή στο τοπικό inbox" }));
    await screen.findByText("Lost response");
    expect(newReport().disabled).toBe(true);
    expect(
      (screen.getByRole("combobox", { name: "Αποθηκευμένα προσχέδια" }) as HTMLSelectElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(
      screen.getByRole("button", { name: "Έλεγχος / επανάληψη του ίδιου αιτήματος" }),
    );
    await screen.findByRole("button", { name: "Το αίτημα αποστολής καταχωρήθηκε" });
    const sends = api.fetch.mock.calls.filter(
      ([url, init]) => url.endsWith("/submissions") && init?.method === "POST",
    );
    expect(sends).toHaveLength(2);
    expect(sends[0][1]?.headers).toEqual(sends[1][1]?.headers);
    expect(newReport().disabled).toBe(false);
  });

  it("shows refresh failure, recovers, and distinguishes queueing from delivery", async () => {
    const api = setup();
    await prepare();
    fireEvent.click(screen.getByRole("button", { name: "Αποστολή στο τοπικό inbox" }));
    await screen.findByRole("button", { name: "Το αίτημα αποστολής καταχωρήθηκε" });
    expect(screen.queryAllByText(/Παραδόθηκε στο τοπικό inbox/)).toHaveLength(0);
    api.failPolling(true);
    await screen.findByText(/Δεν είναι δυνατή η ενημέρωση της κατάστασης/, {}, { timeout: 5000 });
    api.failPolling(false);
    api.setStatus("CAPTURED_LOCAL");
    await waitFor(
      () => expect(screen.getAllByText(/Παραδόθηκε στο τοπικό inbox/)).toHaveLength(2),
      { timeout: 5000 },
    );
    expect(screen.queryByText(/Δεν είναι δυνατή η ενημέρωση της κατάστασης/)).toBeNull();
    expect(screen.getAllByRole("link", { name: /Άνοιγμα τοπικού inbox Mailpit/ })).toHaveLength(2);
  }, 10000);
});
