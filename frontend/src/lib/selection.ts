/**
 * Selection Gate domain rules (issue #28): the Creator picks a rectangle —
 * a set of Clips × a set of Target Languages — or the empty selection.
 * Totals are exact (integer micro-USD via `lib/money.ts`).
 */
import { sumUsd } from "./money";
import type { CostCell } from "./types";

/** A rectangle selection: every selected Clip × every selected Language. */
export interface GateSelection {
  clips: ReadonlySet<number>;
  languages: ReadonlySet<string>;
}

/** Valid when both sides are non-empty (a rectangle) or both are empty (skip localization). */
export function isValidSelection(sel: GateSelection): boolean {
  return (sel.clips.size === 0) === (sel.languages.size === 0);
}

/** Exact total of the selected cells as a wire USD string. */
export function selectionTotal(matrix: readonly CostCell[], sel: GateSelection): string {
  return sumUsd(
    matrix
      .filter((c) => sel.clips.has(c.segment_id) && sel.languages.has(c.language))
      .map((c) => c.total_usd),
  );
}
