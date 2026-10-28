import { describe, it, expect } from "vitest";
import { EMPTY_VALUE, formatDateTime, joinOrEmpty, orEmpty, statusLabel } from "@/lib/format";
import { de, en, es } from "@/lib/i18n";

describe("display formatting", () => {
  it("formats dates for the UI language", () => {
    const iso = "2026-10-27T14:05:00Z";
    expect(formatDateTime(iso, en.locale, "UTC")).toMatch(/^Oct 27, 2026, 2:05\sPM$/);
    expect(formatDateTime(iso, de.locale, "UTC")).toBe("27.10.2026, 14:05");
    expect(formatDateTime(iso, es.locale, "UTC")).toMatch(/^27 oct 2026, 14:05$/);
  });

  it("shows the empty placeholder for missing or invalid values", () => {
    expect(formatDateTime(null, "en")).toBe(EMPTY_VALUE);
    expect(formatDateTime("not a date", "en")).toBe(EMPTY_VALUE);
    expect(orEmpty(null)).toBe(EMPTY_VALUE);
    expect(orEmpty(0)).toBe("0");
    expect(joinOrEmpty([])).toBe(EMPTY_VALUE);
    expect(joinOrEmpty(["es", "de"])).toBe("es, de");
  });

  it("labels Job statuses in the UI language", () => {
    expect(statusLabel(en, "AWAITING_SELECTION")).toBe("Awaiting selection");
    expect(statusLabel(de, "FAILED")).toBe("Fehlgeschlagen");
  });
});
