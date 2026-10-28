/**
 * Display formatting shared by every page: the placeholder for a missing
 * value and locale-aware dates (US15). Money goes through `formatUsd` in
 * `lib/money.ts`.
 */

import type { Dict } from "./i18n";
import type { JobStatus } from "./types";

const STATUS_KEYS: Record<JobStatus, string> = {
  RECEIVED: "received",
  PROCESSING: "processing",
  AWAITING_SELECTION: "pending",
  COMPLETED: "completed",
  FAILED: "failed",
  EXPIRED: "expired",
  CANCELLED: "cancelled",
};

/** Translated label for a Job status, e.g. AWAITING_SELECTION -> "Awaiting selection". */
export function statusLabel(t: Dict, status: JobStatus): string {
  return t[STATUS_KEYS[status]] ?? status;
}

/** Shown wherever a value is absent (no stage yet, no languages, ...). */
export const EMPTY_VALUE = "—";

/** `value` as text, or `EMPTY_VALUE` when it is null, undefined or empty. */
export function orEmpty(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? EMPTY_VALUE : String(value);
}

/** A list joined with ", ", or `EMPTY_VALUE` when it is empty. */
export function joinOrEmpty(values: readonly (string | number)[]): string {
  return values.length ? values.join(", ") : EMPTY_VALUE;
}

/**
 * A wire ISO timestamp as a date and time in `locale` (the current UI
 * language), in the viewer's time zone unless `timeZone` is given.
 * Missing or unparseable timestamps render as `EMPTY_VALUE`.
 */
export function formatDateTime(iso: string | null | undefined, locale: string, timeZone?: string): string {
  if (!iso) return EMPTY_VALUE;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EMPTY_VALUE;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone }).format(d);
}
