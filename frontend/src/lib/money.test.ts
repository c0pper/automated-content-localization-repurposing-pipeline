import { describe, it, expect } from "vitest";
import { formatUsd, sumUsd } from "@/lib/money";

describe("USD decimal-string arithmetic", () => {
  it("sums wire amounts exactly, without float drift", () => {
    // 0.1 + 0.2 in floats is 0.30000000000000004.
    expect(sumUsd(["0.1", "0.2"])).toBe("0.30");
    expect(sumUsd(["0.123456", "0.000001"])).toBe("0.123457");
    expect(sumUsd(["1.50", "2.250000", "10"])).toBe("13.75");
  });

  it("returns 0.00 for an empty sum", () => {
    expect(sumUsd([])).toBe("0.00");
  });

  it("rejects malformed amounts instead of guessing", () => {
    expect(() => sumUsd(["1.2345678"])).toThrow();
    expect(() => sumUsd(["abc"])).toThrow();
    expect(() => sumUsd(["-1.00"])).toThrow();
  });

  it("formats an amount for display with a dollar sign", () => {
    expect(formatUsd("1.250000")).toBe("$1.25");
    expect(formatUsd("0.123456")).toBe("$0.123456");
  });
});
