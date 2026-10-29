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
    expect(formatUsd("1.250000", "en")).toBe("$1.25");
    expect(formatUsd("0.123456", "en")).toBe("$0.123456");
  });

  it("formats an amount for the UI locale without losing micro-USD digits", () => {
    // Intl separates the amount from the symbol with a no-break space.
    expect(formatUsd("1234.5", "de").replace(/\s/g, " ")).toBe("1.234,50 $");
    expect(formatUsd("1234.5", "es").replace(/\s/g, " ")).toBe("1234,50 US$");
    expect(formatUsd("9007199254740993.000001", "en")).toBe("$9,007,199,254,740,993.000001");
    expect(formatUsd("0.123456", "de").replace(/\s/g, " ")).toBe("0,123456 $");
  });
});
