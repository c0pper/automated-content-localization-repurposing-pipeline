import { describe, it, expect } from "vitest";
import { ApiError } from "@/lib/api";
import { errorCodeText, errorText } from "@/lib/errors";
import { de, en } from "@/lib/i18n";

describe("error code messages", () => {
  it.each([
    "selection_price_changed",
    "quality_floor_not_met",
    "voice_profile_missing",
    "lip_sync_unavailable",
    "insufficient_job_budget",
    "workspace_budget_exceeded",
    "invalid_model",
    "caption_alignment_unavailable",
    "no_reviewable_assets",
    "source_too_large",
    "unsupported_media_format",
    "upload_size_mismatch",
    "upload_failed",
    "upload_not_in_progress",
    "upload_parts_invalid",
  ])("has a specific message for %s", (code) => {
    expect(errorCodeText(en, code)).not.toContain("error code");
    expect(errorCodeText(en, code, "job")).not.toContain("error code");
  });

  it("explains lip-sync differently for a rejected request and a failed Job", () => {
    expect(errorCodeText(en, "lip_sync_unavailable")).toContain("Turn off lip-sync to submit");
    expect(errorCodeText(en, "lip_sync_unavailable", "job")).toContain("the whole job stopped");
  });

  it("names unknown codes and never uses the backend message", () => {
    const err = new ApiError(422, "brand_new_code", "raw backend text");
    expect(errorText(en, err)).toBe("Something went wrong (error code: brand_new_code).");
    expect(errorText(de, err)).toBe("Etwas ist schiefgelaufen (Fehlercode: brand_new_code).");
  });

  it("uses the generic message when there was no response", () => {
    expect(errorText(en, new TypeError("Failed to fetch"))).toBe("The request could not be completed. Try again.");
  });
});
