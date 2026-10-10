import { describe, it, expect, vi, afterEach } from "vitest";
import {
  emptyReport,
  yc,
  YellowCardHttpError,
  isDefiniteRejection,
  withReporterDefaults,
  removedReporterDetails,
  asPharmacistReporter,
  type ReportData,
  type StoredReportData,
} from "./yellowCards";
afterEach(() => vi.unstubAllGlobals());
describe("Reporter role compatibility", () => {
  const base = () => emptyReport("Pharmacist", "demo@example.com");
  it("defaults a new report and a legacy draft without reporter keys to private pharmacist", () => {
    expect(base()).toMatchObject({
      reporter_type: "private_pharmacist",
      reporter_specialty: "",
      reporter_other: "",
    });
    const legacy: StoredReportData = base();
    delete legacy.reporter_type;
    delete legacy.reporter_specialty;
    delete legacy.reporter_other;
    expect(withReporterDefaults(legacy)).toMatchObject({
      reporter_type: "private_pharmacist",
      reporter_specialty: "",
      reporter_other: "",
    });
  });
  it("keeps every present value, including null and unrecognized roles", () => {
    const saved = { ...base(), reporter_type: "hospital_doctor", reporter_specialty: "Παθολόγος" };
    expect(withReporterDefaults(saved as ReportData)).toEqual(saved);
    for (const odd of [null, "nurse"]) {
      const data = { ...base(), reporter_type: odd, reporter_other: null };
      const result = withReporterDefaults(data as unknown as ReportData);
      expect(result.reporter_type).toBe(odd);
      expect(result.reporter_other).toBeNull();
    }
  });
  it("names every detail a pharmacist role would remove, including stray ones", () => {
    expect(removedReporterDetails(base())).toEqual([]);
    expect(
      removedReporterDetails({
        ...base(),
        reporter_type: "private_pharmacist",
        reporter_specialty: "Χ",
        reporter_other: "Ψ",
      }),
    ).toEqual([
      ["reporter_specialty", "Χ"],
      ["reporter_other", "Ψ"],
    ]);
  });
  it("changes the role and both details together without touching other fields", () => {
    const doctor = {
      ...base(),
      initials: "Δ.Α.",
      reporter_type: "private_doctor" as const,
      reporter_specialty: "Γενική Ιατρική",
    };
    expect(asPharmacistReporter(doctor, "hospital_pharmacist")).toEqual({
      ...doctor,
      reporter_type: "hospital_pharmacist",
      reporter_specialty: "",
      reporter_other: "",
    });
    expect(doctor.reporter_type).toBe("private_doctor");
  });
});
describe("Yellow Card client", () => {
  it("starts without patient identifiers and keeps independent array values", () => {
    const a = emptyReport("Pharmacist", "demo@example.com"),
      b = emptyReport("Other", "");
    a.suspected[0].name = "changed";
    expect(b.suspected[0].name).toBe("");
    expect(a).not.toHaveProperty("amka");
    expect(a).not.toHaveProperty("rx_id");
    expect(a.report_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
  it("sends approval with cookies and the caller's stable idempotency key", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: "one" }), { status: 202 }));
    vi.stubGlobal("fetch", fetch);
    await yc("/submissions", "POST", { preview_id: "p", approved: true }, "stable");
    expect(fetch).toHaveBeenCalledWith(
      "/yellow-cards/submissions",
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({ "Idempotency-Key": "stable" }),
      }),
    );
  });
  it("surfaces incomplete-report errors instead of demo success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { missing: ["Αρχικά ασθενούς"] } }), {
          status: 422,
        }),
      ),
    );
    await expect(yc("/p/previews", "POST", {})).rejects.toThrow("Αρχικά ασθενούς");
  });
});

describe("Submission outcome classification", () => {
  it.each([401, 403, 409, 422])("recognizes a definite HTTP %i rejection", (status) => {
    expect(isDefiniteRejection(new YellowCardHttpError(status, "rejected"))).toBe(true);
  });
  it.each([408, 500, 502, 503])("preserves uncertainty after HTTP %i", (status) => {
    expect(isDefiniteRejection(new YellowCardHttpError(status, "uncertain"))).toBe(false);
  });
  it("preserves uncertainty after a lost connection or invalid response body", () => {
    expect(isDefiniteRejection(new TypeError("network"))).toBe(false);
    expect(isDefiniteRejection(new SyntaxError("invalid response"))).toBe(false);
  });
});
