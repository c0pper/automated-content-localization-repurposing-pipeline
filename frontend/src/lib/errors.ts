/**
 * The one place backend error codes become user-facing text. The UI maps
 * `ApiError.code` / `Job.error.code` to an i18n key and never renders backend
 * message text; unknown codes get a generic message that names the code.
 */
import { isApiError } from "./api";
import { interpolate } from "./useTranslation";
import type { Dict } from "./i18n";

/**
 * Where the code was seen. `request` is a rejected API call; `job` is a Job
 * that FAILED with that code; `voice` is a Voice Profile save, whose
 * validation errors are about the voice ID.
 */
export type ErrorContext = "request" | "job" | "voice";

type Entry = string | Partial<Record<ErrorContext, string>> & { request: string };

/** Error code -> i18n key, optionally refined per context. */
const ERROR_KEYS: Record<string, Entry> = {
  // Selection Gate
  selection_price_changed: "errorSelectionPriceChanged",
  invalid_state: "gateErrorInvalidState",
  selection_expired: "gateErrorExpired",
  selection_already_confirmed: "gateErrorAlreadyConfirmed",
  invalid_selection: "gateErrorInvalidSelection",
  invalid_amount: "gateErrorInvalidAmount",
  not_found: "jobNotFound",
  // Job failures and submission rejections
  quality_floor_not_met: "errorQualityFloorNotMet",
  voice_profile_missing: "voiceProfileMissing",
  lip_sync_unavailable: { request: "lipSyncUnavailable", job: "jobErrorLipSync" },
  caption_alignment_unavailable: "jobErrorCaptionAlignment",
  insufficient_job_budget: "errorInsufficientJobBudget",
  workspace_budget_exceeded: "budgetExceeded",
  minute_budget_exceeded: "errorMinuteBudgetExceeded",
  character_budget_exceeded: "errorCharacterBudgetExceeded",
  invalid_model: "invalidModel",
  media_too_long: "errorMediaTooLong",
  empty_media: "errorEmptyMedia",
  unsupported_media_format: "errorUnsupportedMediaFormat",
  source_too_large: "errorSourceTooLarge",
  unsafe_source: "errorUnsafeSource",
  invalid_object_key: "errorInvalidObjectKey",
  // Source Upload (lib/sourceUpload.ts)
  upload_size_mismatch: "errorUploadSizeMismatch",
  upload_failed: "errorUploadFailed",
  upload_not_in_progress: "errorUploadFailed",
  upload_parts_invalid: "errorUploadFailed",
  unsupported_language: "errorUnsupportedLanguage",
  invalid_language: "errorUnsupportedLanguage",
  unsupported_source_language: "errorUnsupportedSourceLanguage",
  source_target_conflict: "errorSourceTargetConflict",
  not_retryable: "errorNotRetryable",
  idempotency_in_progress: "errorRequestInProgress",
  validation_error: { request: "errorValidation", voice: "voiceErrorInvalidProfile" },
  // Review link
  no_reviewable_assets: "reviewErrorNoAssets",
  // Voice Profile
  unsupported_voice_provider: "voiceErrorUnsupportedProvider",
  invalid_voice_profile: "voiceErrorInvalidProfile",
};

/** The i18n key for `code` in `context`, or undefined for an unmapped code. */
export function errorKey(code: string, context: ErrorContext = "request"): string | undefined {
  const entry = ERROR_KEYS[code];
  if (entry === undefined) return undefined;
  if (typeof entry === "string") return entry;
  return entry[context] ?? entry.request;
}

/** User-facing text for a backend error code; unmapped codes name the code. */
export function errorCodeText(t: Dict, code: string, context: ErrorContext = "request"): string {
  const key = errorKey(code, context);
  return key && t[key] ? t[key] : interpolate(t.errorWithCode, { code });
}

/** User-facing text for a thrown error: mapped by code, or generic (network failures). */
export function errorText(t: Dict, err: unknown, context: ErrorContext = "request"): string {
  return isApiError(err) ? errorCodeText(t, err.code, context) : t.errorGeneric;
}
