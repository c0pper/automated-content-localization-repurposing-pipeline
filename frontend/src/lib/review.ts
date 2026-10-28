/**
 * Review access domain (issue #32): URL construction for review links.
 *
 * The backend `review_url` (`<api_base_url>/api/review/<token>`) is a JSON
 * endpoint, so the shareable link is the read-only in-app review page
 * `#/review/<token>`, which loads the manifest and plays assets through the
 * stable `/api/review/<token>/assets/<asset_id>` 302 routes. Rotation and
 * revocation live in `jobStore.rotateReviewLink` / `revokeReviewLink`.
 */
import { api } from "./api";
import type { ReviewManifest } from "./types";

export { reviewAssetUrl } from "./api";

/** GET /api/review/{token} (no auth). A revoked or unknown token rejects with a 404 ApiError. */
export function loadReviewManifest(token: string, signal?: AbortSignal): Promise<ReviewManifest> {
  return api.get<ReviewManifest>(`/review/${encodeURIComponent(token)}`, { signal });
}

const REVIEW_PATH = /\/api\/review\/([^/?#]+)/;

/** The token in a backend `review_url`, or null when there is none. */
export function reviewTokenFromUrl(reviewUrl: string | null | undefined): string | null {
  if (!reviewUrl) return null;
  const match = REVIEW_PATH.exec(reviewUrl);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

/** Hash link to the in-app review page for a `review_url`, or null when there is no token. */
export function openReviewLink(reviewUrl: string | null | undefined): string | null {
  const token = reviewTokenFromUrl(reviewUrl);
  return token ? `#/review/${encodeURIComponent(token)}` : null;
}
