import { describe, expect, it } from "vitest";
import { errorMessageFromDetail } from "./api";

describe("errorMessageFromDetail", () => {
  it("returns a plain string detail unchanged", () => {
    expect(errorMessageFromDetail(400, "Pharmacy not found")).toBe("Pharmacy not found");
  });

  it("falls back to HTTP <status> for missing/empty/blank detail", () => {
    expect(errorMessageFromDetail(500, undefined)).toBe("HTTP 500");
    expect(errorMessageFromDetail(500, "")).toBe("HTTP 500");
    expect(errorMessageFromDetail(500, "   ")).toBe("HTTP 500");
  });

  it("formats a Pydantic 422 array as field: message", () => {
    const detail = [{ loc: ["body", "name"], msg: "must not be blank", type: "value_error" }];
    expect(errorMessageFromDetail(422, detail)).toBe("name: must not be blank");
  });

  it("joins multiple validation errors with '; '", () => {
    const detail = [
      { loc: ["body", "conditionCode"], msg: "field required", type: "missing" },
      { loc: ["body", "name"], msg: "must not be blank", type: "value_error" },
    ];
    expect(errorMessageFromDetail(422, detail)).toBe(
      "conditionCode: field required; name: must not be blank",
    );
  });

  it("strips Pydantic's 'Value error, ' prefix", () => {
    const detail = [
      { loc: ["body", "name"], msg: "Value error, cannot be null", type: "value_error" },
    ];
    expect(errorMessageFromDetail(422, detail)).toBe("name: cannot be null");
  });

  it("uses the bare msg when loc is absent", () => {
    expect(errorMessageFromDetail(422, [{ msg: "something went wrong" }])).toBe(
      "something went wrong",
    );
  });

  it("never yields [object Object]", () => {
    const detail = [{ loc: ["body", "name"], msg: "must not be blank" }];
    expect(errorMessageFromDetail(422, detail)).not.toContain("[object Object]");
  });

  it("falls back for unexpected shapes (object, or array of junk)", () => {
    expect(errorMessageFromDetail(418, { unexpected: true })).toBe("HTTP 418");
    expect(errorMessageFromDetail(418, [{ type: "x" }, 42])).toBe("HTTP 418");
  });
});
