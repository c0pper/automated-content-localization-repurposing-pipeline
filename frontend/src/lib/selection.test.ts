import { describe, it, expect } from "vitest";
import { isValidSelection, selectionTotal } from "@/lib/selection";
import type { CostCell } from "@/lib/types";

const cell = (segment_id: number, language: string, total_usd: string): CostCell => ({
  segment_id,
  language,
  translation_usd: "0.00",
  voice_usd: "0.00",
  lip_sync_usd: "0.00",
  total_usd,
});

describe("Selection Gate rules", () => {
  it("accepts a rectangle or the empty selection, never one side alone", () => {
    expect(isValidSelection({ clips: new Set([1]), languages: new Set(["es"]) })).toBe(true);
    expect(isValidSelection({ clips: new Set(), languages: new Set() })).toBe(true);
    expect(isValidSelection({ clips: new Set([1]), languages: new Set() })).toBe(false);
    expect(isValidSelection({ clips: new Set(), languages: new Set(["es"]) })).toBe(false);
  });

  it("sums exactly the selected cells", () => {
    const matrix = [cell(1, "es", "0.10"), cell(1, "de", "0.200001"), cell(2, "es", "0.30"), cell(2, "de", "5.00")];
    expect(selectionTotal(matrix, { clips: new Set([1]), languages: new Set(["es", "de"]) })).toBe("0.300001");
    expect(selectionTotal(matrix, { clips: new Set(), languages: new Set() })).toBe("0.00");
  });
});
