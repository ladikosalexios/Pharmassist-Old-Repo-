import { describe, it, expect, vi, afterEach } from "vitest";
import { emptyReport, yc, YellowCardHttpError, isDefiniteRejection } from "./yellowCards";
afterEach(() => vi.unstubAllGlobals());
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
