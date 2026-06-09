import { describe, expect, it } from "vitest";
import { isCompletePack, parseGs1 } from "./gs1";

const GS = String.fromCharCode(0x1d);

describe("parseGs1", () => {
  it("decodes a fixed-then-variable payload terminated by FNC1", () => {
    // (01)05700123456789 (21)9d8X7p17 ⓖ (10)B-4471 ⓖ (17)270531
    const payload = `010570012345678921` + `9d8X7p17` + GS + `10B-4471` + GS + `17270531`;
    expect(parseGs1(payload)).toEqual({
      gtin: "05700123456789",
      serial: "9d8X7p17",
      batch: "B-4471",
      expiry: "270531",
    });
  });

  it("strips the AIM `]d2` symbology prefix", () => {
    const payload = `]d2010570012345678921ABC123` + GS + `10LOT1` + GS + `17260101`;
    const out = parseGs1(payload);
    expect(out.gtin).toBe("05700123456789");
    expect(out.serial).toBe("ABC123");
    expect(out.batch).toBe("LOT1");
    expect(out.expiry).toBe("260101");
  });

  it("tolerates a leading FNC1 before the first AI", () => {
    const payload = `${GS}010570012345678921ABC123${GS}17260101`;
    const out = parseGs1(payload);
    expect(out.gtin).toBe("05700123456789");
    expect(out.serial).toBe("ABC123");
    expect(out.expiry).toBe("260101");
  });

  it("accepts variable-length AI terminated by end of string", () => {
    // No trailing GS — last AI runs to end of payload.
    const payload = `010570012345678921ABCDEFG`;
    expect(parseGs1(payload)).toEqual({
      gtin: "05700123456789",
      serial: "ABCDEFG",
    });
  });

  it("aborts on an unknown AI rather than silently skipping", () => {
    // AI 99 is unknown — parse should stop after the GTIN.
    const payload = `010570012345678999XYZ`;
    expect(parseGs1(payload).gtin).toBe("05700123456789");
    expect(parseGs1(payload).serial).toBeUndefined();
  });

  it("rejects non-digit characters in fixed-length AIs (01, 17)", () => {
    // A garbled GTIN with a letter — the upstream would 404 / 422 the lookup.
    // The parser drops the field locally so isCompletePack stays false and the
    // scanner shows "scanMalformed" without a phone-home round-trip.
    expect(parseGs1("0105700X23456789").gtin).toBeUndefined();
    expect(parseGs1("17270A31").expiry).toBeUndefined();
  });

  it("tolerates the combined AIM prefix + leading FNC1 (Zebra style)", () => {
    // Some Zebra-class scanners emit `]d2` then a stray FNC1 before the first AI.
    const payload = `]d2${GS}010570012345678921ABC123${GS}17260101`;
    const out = parseGs1(payload);
    expect(out.gtin).toBe("05700123456789");
    expect(out.serial).toBe("ABC123");
    expect(out.expiry).toBe("260101");
  });

  it("isCompletePack flips only when all four AIs are present", () => {
    expect(isCompletePack({ gtin: "g", serial: "s", batch: "b", expiry: "e" })).toBe(true);
    expect(isCompletePack({ gtin: "g", serial: "s", batch: "b" })).toBe(false);
    expect(isCompletePack({})).toBe(false);
  });
});
