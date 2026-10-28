import { describe, it, expect, vi, beforeEach } from "vitest";
import { createJobStore } from "@/store/jobStore";
import type { GatePayload, JobSummary } from "@/lib/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, details: Record<string, unknown> = {}): Response {
  return jsonResponse({ detail: { code, message: "backend text", details } }, status);
}

const keyOf = (call: unknown[]) => new Headers((call[1] as RequestInit).headers).get("Idempotency-Key");

function summary(job_id: string, status: JobSummary["status"] = "COMPLETED"): JobSummary {
  return { job_id, status, stage: null, created_at: null, expires_at: null, review_url: null };
}

describe("JobStore", () => {
  let store: ReturnType<typeof createJobStore>;
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    store = createJobStore();
    mockFetch = vi.fn();
    globalThis.fetch = mockFetch;
  });

  it("lists jobs", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [], next_cursor: null }));
    await store.getState().listJobs();
    expect(store.getState().loading).toBe(false);
    expect(store.getState().jobs).toEqual([]);
  });

  it("initializes with empty state", () => {
    expect(store.getState().jobs.length).toBe(0);
    expect(store.getState().nextCursor).toBeNull();
    expect(store.getState().busy).toBe(false);
    expect(store.getState().selectedJob).toBeNull();
  });

  it("discards a late 'load more' page when the status filter changed meanwhile", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [summary("job_p1", "PROCESSING")], next_cursor: "cur_2" }));
    await store.getState().listJobs({ status: "PROCESSING" });

    let releaseMore!: (r: Response) => void;
    mockFetch.mockReturnValueOnce(new Promise<Response>((resolve) => (releaseMore = resolve)));
    const more = store.getState().listJobs({ status: "PROCESSING", cursor: "cur_2", append: true });

    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [summary("job_f1", "FAILED")], next_cursor: null }));
    await store.getState().listJobs({ status: "FAILED" });

    releaseMore(jsonResponse({ items: [summary("job_p2", "PROCESSING")], next_cursor: "cur_3" }));
    await more;

    expect(store.getState().jobs.map((j) => j.job_id)).toEqual(["job_f1"]);
    expect(store.getState().nextCursor).toBeNull();
  });

  describe("idempotent retries (ADR-0019)", () => {
    it("reuses the Idempotency-Key when the same selection is retried after a network failure", async () => {
      mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
      mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: "job_1", status: "PROCESSING" }, 202));

      await expect(store.getState().confirmSelection("job_1", [1], ["es"], "0.30")).rejects.toThrow();
      await store.getState().confirmSelection("job_1", [1], ["es"], "0.30");

      expect(keyOf(mockFetch.mock.calls[0])).toBeTruthy();
      expect(keyOf(mockFetch.mock.calls[1])).toBe(keyOf(mockFetch.mock.calls[0]));
    });

    it("reuses the key after a 5xx, but not once the request succeeded", async () => {
      mockFetch.mockResolvedValueOnce(errorResponse(503, "internal_error"));
      mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: "job_1", status: "CANCELLED" }));
      mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: "job_1", status: "CANCELLED" }));

      await expect(store.getState().cancelJob("job_1")).rejects.toThrow();
      await store.getState().cancelJob("job_1");
      await store.getState().cancelJob("job_1");

      const [first, retry, again] = mockFetch.mock.calls.map(keyOf);
      expect(retry).toBe(first);
      expect(again).not.toBe(first);
    });

    it("uses a new key when the inputs change", async () => {
      mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
      mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: "job_1", status: "PROCESSING" }, 202));

      await expect(store.getState().confirmSelection("job_1", [1], ["es"], "0.30")).rejects.toThrow();
      await store.getState().confirmSelection("job_1", [1, 2], ["es"], "0.60");

      expect(keyOf(mockFetch.mock.calls[1])).not.toBe(keyOf(mockFetch.mock.calls[0]));
    });

    it("uses a new key after a definitive rejection, so a later attempt is not a replay", async () => {
      mockFetch.mockResolvedValueOnce(errorResponse(409, "no_reviewable_assets"));
      mockFetch.mockResolvedValueOnce(jsonResponse({ review_url: "http://x/api/review/tok", rotated_at: "t" }));

      await expect(store.getState().rotateReviewLink("job_1")).rejects.toThrow();
      await store.getState().rotateReviewLink("job_1");

      expect(keyOf(mockFetch.mock.calls[1])).not.toBe(keyOf(mockFetch.mock.calls[0]));
    });

    it("reuses the key for a retried job submission and review-link revoke", async () => {
      const payload = {
        source: { type: "url" as const, url: "https://example.com/a.mp4" },
        target_languages: ["es"],
        lip_sync: false,
        model_overrides: {},
      };
      mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
      mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: "job_2", status: "RECEIVED", created_at: "t" }, 202));
      mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
      mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));

      await expect(store.getState().submitJob(payload)).rejects.toThrow();
      await store.getState().submitJob({ ...payload });
      await expect(store.getState().revokeReviewLink("job_2")).rejects.toThrow();
      await store.getState().revokeReviewLink("job_2");

      const keys = mockFetch.mock.calls.map(keyOf);
      expect(keys[1]).toBe(keys[0]);
      expect(keys[3]).toBe(keys[2]);
      expect(keys[2]).not.toBe(keys[0]);
    });
  });

  it("on 409 selection_price_changed reloads the gate and rethrows", async () => {
    const gate = {
      job_id: "job_1",
      cost_matrix: [{ segment_id: 1, language: "es", translation_usd: "0.10", voice_usd: "0.20", lip_sync_usd: "0", total_usd: "0.30" }],
    } as unknown as GatePayload;
    store.setState({ gate });
    mockFetch.mockResolvedValueOnce(
      errorResponse(409, "selection_price_changed", {
        current_total_usd: "0.40",
        cost_matrix: [{ segment_id: 1, language: "es", total_usd: "0.40" }],
        projected_total_usd: "0.40",
      }),
    );
    // Reloading the full gate fails: the cell totals are patched from the 409 details instead.
    mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(store.getState().confirmSelection("job_1", [1], ["es"], "0.30")).rejects.toMatchObject({
      code: "selection_price_changed",
    });
    expect(store.getState().gate?.cost_matrix[0].total_usd).toBe("0.40");
    expect(String(mockFetch.mock.calls[1][0])).toContain("/api/jobs/job_1/selection");
  });
});
