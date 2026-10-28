/**
 * Thin fetch wrapper around the FastAPI REST contracts under /api.
 *
 * Auth is cookie-based (JWT in httpOnly cookie) — the browser attaches it
 * automatically. Refresh rotation is handled transparently on 401 responses.
 * POST/DELETE mutations require an Idempotency-Key header.
 */

import type { ApiErrorDetail } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

/**
 * Stable, cookie-authenticated URL for a Job asset. The backend answers with a
 * 302 to a short-lived presigned URL, so the link never goes stale the way a
 * raw object-store URL does. Asset ids: `base_{segment}`,
 * `clip_{segment}_{lang}`, `copy_linkedin`, `copy_newsletter`.
 */
export function jobAssetUrl(jobId: string, assetId: string): string {
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/assets/${encodeURIComponent(assetId)}`;
}

let _csrfCounter = 0;
function generateIdempotencyKey(): string {
  _csrfCounter += 1;
  const rand = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
  return `idem_${Date.now().toString(36)}_${_csrfCounter}_${rand.slice(0, 8)}`;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  retryable: boolean;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    retryable = false,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryable = retryable;
  }
}

function parseError(body: unknown): ApiError {
  const detail = (body as { detail?: ApiErrorDetail })?.detail;
  if (detail && typeof detail === "object" && typeof detail.code === "string") {
    return new ApiError(0, detail.code, detail.message ?? detail.code, detail.details ?? {});
  }
  return new ApiError(0, "internal_error", typeof body === "string" ? body : "Request failed");
}

async function readError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.clone().json();
  } catch {
    try {
      body = await res.clone().text();
    } catch {
      /* ignore */
    }
  }
  const err = parseError(body);
  err.status = res.status;
  return err;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  idempotent?: boolean;
  signal?: AbortSignal;
}

function buildQuery(
  query: Record<string, string | number | boolean | null | undefined> | undefined,
): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined) continue;
    params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `?${suffix}` : "";
}

let _refreshInFlight: Promise<void> | null = null;

async function refreshSession(): Promise<void> {
  if (_refreshInFlight) {
    await _refreshInFlight;
    return;
  }
  _refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        throw new ApiError(res.status, "session_expired", "Session expired; please log in again");
      }
    } finally {
      _refreshInFlight = null;
    }
  })();
  await _refreshInFlight;
}

export const api = {
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? "GET";
    const url = `${API_BASE}${path}${buildQuery(options.query)}`;
    const headers = new Headers();
    headers.set("Accept", "application/json");
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    if (options.idempotent !== false && (method === "POST" || method === "DELETE")) {
      headers.set("Idempotency-Key", generateIdempotencyKey());
    }

    const doFetch = (signal?: AbortSignal) =>
      fetch(url, {
        method,
        headers,
        credentials: "include",
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        signal,
      });

    let res = await doFetch(options.signal);
    if (res.status === 401) {
      try {
        await refreshSession();
      } catch {
        throw await readError(res);
      }
      res = await doFetch(options.signal);
    }

    if (!res.ok) {
      throw await readError(res);
    }

    if (res.status === 204) return undefined as unknown as T;
    const text = await res.text();
    if (!text) return undefined as unknown as T;
    return JSON.parse(text) as T;
  },

  get<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  },
  post<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  },
  put<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "PUT", body });
  },
  delete<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  },
};

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error instanceof ApiError) return error.message || fallback;
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}

export function isRetryableError(error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.retryable) return true;
    if (error.status >= 500) return true;
    return ["internal_error", "workspace_budget_exceeded", "rate_limit_exceeded"].includes(error.code);
  }
  return false;
}

export function isSelectionPriceChanged(error: unknown): {
  changed: true;
  currentTotalUsd: string;
  costMatrix: { segment_id: number; language: string; total_usd: string }[];
  projectedTotalUsd: string;
} | null {
  if (!(error instanceof ApiError) || error.code !== "selection_price_changed") return null;
  const details = (error.details ?? {}) as Record<string, unknown>;
  const costMatrix = Array.isArray(details.cost_matrix)
    ? (details.cost_matrix as { segment_id: number; language: string; total_usd: string }[])
    : [];
  return {
    changed: true,
    currentTotalUsd: String(details.current_total_usd ?? "0.00"),
    costMatrix,
    projectedTotalUsd: String(details.projected_total_usd ?? "0.00"),
  };
}