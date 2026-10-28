import { describe, expect, it } from "vitest";
import { contrastRatio, meetsWcagAA } from "./contrast";

describe("contrastRatio (WCAG 2.x)", () => {
  it("is 21:1 for white on black and 1:1 for identical colors", () => {
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 5);
    expect(contrastRatio("#000", "#000")).toBeCloseTo(1, 5);
  });

  it("is symmetric and matches published reference values", () => {
    // Reference values: WebAIM contrast checker.
    expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
    expect(contrastRatio("#ffffff", "#777777")).toBeCloseTo(4.48, 2);
    expect(contrastRatio("#00ffff", "#000000")).toBeCloseTo(16.75, 2);
  });

  it("applies the AA thresholds (4.5:1 normal text, 3:1 large text)", () => {
    expect(meetsWcagAA("#777777", "#ffffff")).toBe(false);
    expect(meetsWcagAA("#777777", "#ffffff", { largeText: true })).toBe(true);
    expect(meetsWcagAA("#767676", "#ffffff")).toBe(true);
  });
});
