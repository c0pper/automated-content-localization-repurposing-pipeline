import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError, isApiError, isRetryableError, isSelectionPriceChanged } from "@/lib/api";

describe("api client", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
  });

  it("performs a GET request with credentials", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const result = await api.get("/workspace");
    expect(result).toEqual({ ok: true });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/workspace"),
      expect.objectContaining({
        method: "GET",
        credentials: "include",
      }),
    );
  });

  it("throws ApiError on non-2xx response", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: { code: "not_found", message: "Unknown job" } }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(api.get("/jobs/unknown")).rejects.toThrow(ApiError);
  });

  it("includes Idempotency-Key on POST mutations", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ job_id: "job_1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await api.post("/jobs", { source: { type: "url", url: "http://x" } });
    const headers = mockFetch.mock.calls[0][1].headers as Headers;
    expect(headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("does not add Idempotency-Key on GET requests", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await api.get("/jobs");
    const headers = mockFetch.mock.calls[0][1].headers as Headers;
    expect(headers.get("Idempotency-Key")).toBeNull();
  });

  it("refreshes the session on 401 then retries", async () => {
    mockFetch
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { code: "unauthorized", message: "expired" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { code: "ok" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const result = await api.get("/workspace");
    expect(result).toEqual({ detail: { code: "ok" } });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("parses selection_price_changed error with current total", async () => {
    const payload = {
      detail: {
        code: "selection_price_changed",
        message: "total changed",
        details: {
          current_total_usd: "1.50",
          projected_total_usd: "1.50",
          cost_matrix: [{ segment_id: 1, language: "es", total_usd: "1.50" }],
        },
      },
    };
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(payload), { status: 409, headers: { "Content-Type": "application/json" } }),
    );
    let error: unknown;
    try {
      await api.get("/jobs/x/selection");
    } catch (e) {
      error = e;
    }
    expect(isApiError(error)).toBe(true);
    expect(isRetryableError(error)).toBe(false);
    const changed = isSelectionPriceChanged(error);
    expect(changed).not.toBeNull();
    expect(changed!.currentTotalUsd).toBe("1.50");
    expect(changed!.costMatrix).toHaveLength(1);
  });
});