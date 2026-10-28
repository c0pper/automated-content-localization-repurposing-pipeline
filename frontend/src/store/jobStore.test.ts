import { describe, it, expect, vi, beforeEach } from "vitest";
import { createJobStore } from "@/store/jobStore";

describe("JobStore", () => {
  let store: ReturnType<typeof createJobStore>;

  beforeEach(() => {
    store = createJobStore();
  });

  it("lists jobs", async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
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
});