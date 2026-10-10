import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import i18n from "../lib/i18n";
import en from "../locales/en.json";
import el from "../locales/el.json";
import { YellowCards } from "./YellowCards";
import { emptyReport, type Report, type StoredReportData } from "../lib/yellowCards";

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
  vi.unstubAllEnvs();
});

const submission = {
  id: "send",
  preview_id: "preview",
  status: "QUEUED",
  approved_at: "2026-10-07T13:26:18Z",
  failure_code: null,
};
const previewBody = {
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
};
function setup(
  options: {
    imported?: Report;
    reports?: Report[];
    previews?: () => Response | undefined;
    saveGate?: Promise<void>;
  } = {},
) {
  let status = "QUEUED",
    submitted = false,
    pollingFails = false;
  const post = vi.fn(async () => new Response(JSON.stringify(submission), { status: 202 }));
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    // Drafts echo what was sent, as the API does.
    if (init?.method === "POST" && input === "/yellow-cards") {
      await options.saveGate;
      return Response.json({ id: "draft", revision: 1, data: JSON.parse(String(init.body)) });
    }
    if (init?.method === "PATCH") {
      await options.saveGate;
      const body = JSON.parse(String(init.body));
      return Response.json({
        id: input.split("/").pop(),
        revision: body.revision + 1,
        data: body.data,
      });
    }
    if (input === "/yellow-cards" && options.reports) return Response.json(options.reports);
    if (input.endsWith("/previews")) {
      const custom = options.previews?.();
      if (custom) return custom;
    }
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
    if (input.endsWith("/previews")) return Response.json(previewBody);
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetch);
  const state = options.imported ? { report: options.imported } : null;
  render(
    <MemoryRouter initialEntries={[{ pathname: "/", state }]}>
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
  await requestPreview();
  await screen.findByText("PDF preview");
  fireEvent.click(screen.getByRole("checkbox", { name: /Έλεγξα το PDF/ }));
}
async function requestPreview() {
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

const reporter = () =>
  screen.getByRole("combobox", { name: "Ιδιότητα αναφέροντος" }) as HTMLSelectElement;
const optionTexts = () => Array.from(reporter().options).map((o) => o.textContent);
function draft(changes: Partial<StoredReportData> = {}, revision = 3): Report {
  return {
    id: "saved",
    revision,
    data: { ...emptyReport("Test", "demo@example.com"), initials: "Σ.Δ.", ...changes },
  } as Report;
}
function legacyDraft(): Report {
  const report = draft();
  const data: StoredReportData = report.data;
  delete data.reporter_type;
  delete data.reporter_specialty;
  delete data.reporter_other;
  return report;
}
function sent(api: ReturnType<typeof setup>, method: "POST" | "PATCH") {
  return api.fetch.mock.calls
    .filter(([url, init]) => init?.method === method && !url.includes("/previews"))
    .map(([url, init]) => ({ url, body: JSON.parse(String(init?.body)) }));
}
async function saveDraft() {
  fireEvent.click(screen.getByRole("button", { name: "Αποθήκευση προσχεδίου" }));
  await screen.findByText("Το προσχέδιο αποθηκεύτηκε.");
}
const reporterFields = (data: Record<string, unknown>) => ({
  reporter_type: data.reporter_type,
  reporter_specialty: data.reporter_specialty,
  reporter_other: data.reporter_other,
});
const savedRoles = [
  { reporter_type: "hospital_doctor", reporter_specialty: "Παθολόγος", reporter_other: "" },
  { reporter_type: "private_doctor", reporter_specialty: "Γενική Ιατρική", reporter_other: "" },
  { reporter_type: "other", reporter_specialty: "", reporter_other: "Νοσηλευτής" },
] as const;

describe("Yellow Card reporter role", () => {
  it("offers only pharmacist roles, defaults to private and saves the chosen role", async () => {
    const api = setup();
    const confirm = vi.spyOn(window, "confirm");
    expect(reporter().value).toBe("private_pharmacist");
    expect(optionTexts()).toEqual(["Ιδιώτης φαρμακοποιός", "Νοσοκομειακός φαρμακοποιός"]);
    fireEvent.change(reporter(), { target: { value: "hospital_pharmacist" } });
    expect(confirm).not.toHaveBeenCalled();
    await saveDraft();
    expect(reporterFields(sent(api, "POST")[0].body)).toEqual({
      reporter_type: "hospital_pharmacist",
      reporter_specialty: "",
      reporter_other: "",
    });
  });

  it("saves an imported legacy draft as private pharmacist at its revision", async () => {
    const api = setup({ imported: legacyDraft() });
    expect(reporter().value).toBe("private_pharmacist");
    await saveDraft();
    const [patch] = sent(api, "PATCH");
    expect(patch.url).toBe("/yellow-cards/saved");
    expect(patch.body.revision).toBe(3);
    expect(reporterFields(patch.body.data)).toEqual({
      reporter_type: "private_pharmacist",
      reporter_specialty: "",
      reporter_other: "",
    });
  });

  it("saves a listed legacy draft as private pharmacist at its revision", async () => {
    const api = setup({ reports: [legacyDraft()] });
    const drafts = screen.getByRole("combobox", { name: "Αποθηκευμένα προσχέδια" });
    await screen.findByRole("option", { name: /Σ\.Δ\./ });
    fireEvent.change(drafts, { target: { value: "saved" } });
    expect(reporter().value).toBe("private_pharmacist");
    await saveDraft();
    const [patch] = sent(api, "PATCH");
    expect(patch.body.revision).toBe(3);
    expect(patch.body.data.initials).toBe("Σ.Δ.");
    expect(patch.body.data.reporter_type).toBe("private_pharmacist");
  });

  it.each(savedRoles)("shows and keeps a saved $reporter_type draft unchanged", async (role) => {
    const api = setup({ imported: draft(role) });
    expect(reporter().value).toBe(role.reporter_type);
    expect(optionTexts()[0]).toMatch(/\(αποθηκευμένο στο προσχέδιο\)$/);
    expect(optionTexts()).toHaveLength(3);
    expect(screen.getByRole("note").textContent).toMatch(/Παραμένει ως έχει/);
    screen.getByText(new RegExp(role.reporter_specialty || role.reporter_other));
    await saveDraft();
    const [patch] = sent(api, "PATCH");
    expect(patch.body.revision).toBe(3);
    expect(reporterFields(patch.body.data)).toEqual(role);
  });

  it("keeps an unrecognized saved role visible instead of replacing it", () => {
    setup({ imported: draft({ reporter_type: "nurse" } as unknown as Partial<StoredReportData>) });
    expect(reporter().value).toBe("nurse");
    expect(optionTexts()[0]).toBe("Μη αναγνωρισμένη ιδιότητα: nurse (αποθηκευμένο στο προσχέδιο)");
  });

  it("cancelling a conversion keeps role, details, preview, approval and state", async () => {
    setup({ imported: draft(savedRoles[0]) });
    await prepare();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.change(reporter(), { target: { value: "hospital_pharmacist" } });
    expect(confirm).toHaveBeenCalledOnce();
    expect(confirm.mock.calls[0][0]).toContain("«Νοσοκομειακός φαρμακοποιός»");
    expect(confirm.mock.calls[0][0]).toContain("Ειδικότητα: «Παθολόγος»");
    expect(reporter().value).toBe("hospital_doctor");
    screen.getByText(/Παθολόγος/);
    screen.getByText("PDF preview");
    expect(
      (screen.getByRole("checkbox", { name: /Έλεγξα το PDF/ }) as HTMLInputElement).checked,
    ).toBe(true);
    // Not dirty: starting a new report needs no discard confirmation.
    fireEvent.click(newReport());
    expect(confirm).toHaveBeenCalledOnce();
  });

  it("a confirmed conversion clears both details and invalidates the preview", async () => {
    const api = setup({ imported: draft(savedRoles[2]) });
    await prepare();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.change(reporter(), { target: { value: "hospital_pharmacist" } });
    expect(reporter().value).toBe("hospital_pharmacist");
    expect(optionTexts()).toHaveLength(2);
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText(/Νοσηλευτής/)).toBeNull();
    expect(screen.queryByText("PDF preview")).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /Έλεγξα το PDF/ })).toBeNull();
    await saveDraft();
    const patches = sent(api, "PATCH");
    const last = patches[patches.length - 1];
    expect(last.body.revision).toBe(4);
    expect(reporterFields(last.body.data)).toEqual({
      reporter_type: "hospital_pharmacist",
      reporter_specialty: "",
      reporter_other: "",
    });
  });

  it("names a stray detail saved under a pharmacist role before removing it", async () => {
    const api = setup({
      imported: draft({ reporter_type: "private_pharmacist", reporter_other: "Παλιό κείμενο" }),
    });
    screen.getByText(/Παλιό κείμενο/);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.change(reporter(), { target: { value: "hospital_pharmacist" } });
    expect(confirm.mock.calls[0][0]).toContain("Περιγραφή ιδιότητας: «Παλιό κείμενο»");
    await saveDraft();
    expect(sent(api, "PATCH")[0].body.data.reporter_other).toBe("");
  });

  it.each([
    ...savedRoles,
    { reporter_type: "hospital_pharmacist", reporter_specialty: "", reporter_other: "" },
  ] as const)("the synthetic example keeps a $reporter_type role", async (role) => {
    const api = setup({ imported: draft(role) });
    fireEvent.click(screen.getByRole("button", { name: "Συμπλήρωση συνθετικού παραδείγματος" }));
    expect(reporter().value).toBe(role.reporter_type);
    await saveDraft();
    const [patch] = sent(api, "PATCH");
    expect(patch.body.data.initials).toBe("Δ.Α.");
    expect(reporterFields(patch.body.data)).toEqual(role);
  });

  it("locks the role while a save is in flight", async () => {
    let release = () => {};
    setup({ saveGate: new Promise<void>((resolve) => (release = resolve)) });
    fireEvent.click(screen.getByRole("button", { name: "Αποθήκευση προσχεδίου" }));
    await waitFor(() => expect(reporter().closest("fieldset")!.disabled).toBe(true));
    release();
    await screen.findByText("Το προσχέδιο αποθηκεύτηκε.");
    expect(reporter().closest("fieldset")!.disabled).toBe(false);
  });

  it("locks the role while a submission outcome is uncertain", async () => {
    const api = setup();
    api.post.mockRejectedValueOnce(new TypeError("Lost response"));
    await prepare();
    fireEvent.click(screen.getByRole("button", { name: "Αποστολή στο τοπικό inbox" }));
    await screen.findByText("Lost response");
    expect(reporter().closest("fieldset")!.disabled).toBe(true);
  });

  it("shows the backend's reporter consistency error from preview", async () => {
    setup({
      previews: () =>
        Response.json(
          { detail: { missing: ["Ιδιότητα αναφέροντος και συνεπή στοιχεία"] } },
          { status: 422 },
        ),
    });
    await requestPreview();
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Συμπληρώστε: Ιδιότητα αναφέροντος και συνεπή στοιχεία",
    );
    expect(screen.queryByText("PDF preview")).toBeNull();
  });

  it("drops an approved preview once a save supersedes it, even if re-preview fails", async () => {
    let calls = 0;
    const api = setup({
      previews: () => (++calls > 1 ? new Response(null, { status: 500 }) : undefined),
    });
    await prepare();
    fireEvent.click(screen.getByRole("button", { name: "Δημιουργία και προεπισκόπηση PDF" }));
    await screen.findByText(/Η ενέργεια απέτυχε \(500\)/);
    expect(sent(api, "PATCH")).toHaveLength(1);
    expect(screen.queryByText("PDF preview")).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /Έλεγξα το PDF/ })).toBeNull();
  });

  it("renders the reporter labels in English", async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    try {
      setup({ imported: draft(savedRoles[1]) });
      const select = screen.getByRole("combobox", { name: "Reporter role" }) as HTMLSelectElement;
      expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
        "Private-practice doctor (saved in this draft)",
        "Private pharmacist",
        "Hospital pharmacist",
      ]);
      screen.getByText("Specialty: Γενική Ιατρική");
    } finally {
      await act(async () => {
        await i18n.changeLanguage("el");
      });
    }
  });

  it("has the same reporter keys in Greek and English", () => {
    const keys = (value: object, prefix = ""): string[] =>
      Object.entries(value).flatMap(([k, v]) =>
        typeof v === "object" ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
      );
    expect(keys(el.yellowCards).sort()).toEqual(keys(en.yellowCards).sort());
    expect(keys(en.yellowCards)).toHaveLength(12);
  });
});

describe("Yellow Card local inbox links", () => {
  it.each([
    ["the configured", "http://127.0.0.1:8028", "http://127.0.0.1:8028"],
    ["the default for a blank", "", "http://127.0.0.1:8026"],
  ])(
    "point all three shortcuts at %s inbox",
    async (_, configured, expected) => {
      vi.stubEnv("VITE_YELLOW_CARDS_MAILPIT_URL", configured);
      const api = setup();
      const links = () =>
        screen.getAllByRole("link", { name: /inbox Mailpit/ }) as HTMLAnchorElement[];
      expect(links().map((a) => a.getAttribute("href"))).toEqual([expected]);
      await prepare();
      fireEvent.click(screen.getByRole("button", { name: "Αποστολή στο τοπικό inbox" }));
      await screen.findByRole("button", { name: "Το αίτημα αποστολής καταχωρήθηκε" });
      api.setStatus("CAPTURED_LOCAL");
      // Top shortcut, current captured submission, and history entry.
      await waitFor(() => expect(links()).toHaveLength(3), { timeout: 5000 });
      expect(links().map((a) => a.getAttribute("href"))).toEqual([expected, expected, expected]);
      for (const link of links()) {
        expect(link.target).toBe("_blank");
        fireEvent.click(link);
      }
      // Opening the inbox is navigation only: no further send, preview or draft request.
      const writes = api.fetch.mock.calls.filter(
        ([, init]) => init?.method && init.method !== "GET",
      );
      expect(writes.map(([url]) => url)).toEqual([
        "/yellow-cards",
        "/yellow-cards/draft/previews",
        "/yellow-cards/submissions",
      ]);
    },
    10000,
  );
});
