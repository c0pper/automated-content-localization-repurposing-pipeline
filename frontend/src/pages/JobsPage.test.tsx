import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { JobsPage } from "@/pages/JobsPage";
import { jobStore } from "@/store";
import type { JobSummary } from "@/lib/types";

function job(job_id: string, overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    job_id,
    status: "COMPLETED",
    stage: null,
    created_at: "2026-10-27T00:00:00Z",
    expires_at: null,
    review_url: null,
    ...overrides,
  } as JobSummary;
}

function detail(job_id: string, source: string, targets: string[], hooks: string[] = []) {
  return {
    job_id,
    status: "COMPLETED",
    stage: null,
    source_language: { code: source, origin: "detected", detected_code: source },
    target_languages: targets,
    segments: hooks.map((hook_title, i) => ({ segment_id: i + 1, hook_title })),
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestedUrl(call: unknown[]): URL {
  return new URL(String(call[0]), "http://localhost");
}

type Reply = unknown | (() => Promise<Response>);

/**
 * Routes GET /api/jobs (list) by its `status`/`cursor` query and
 * GET /api/jobs/{id} (details) by id; unknown routes 404.
 */
function routeFetch(lists: Record<string, Reply>, details: Record<string, unknown> = {}) {
  return (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/jobs") {
      const key = `${url.searchParams.get("status") ?? ""}|${url.searchParams.get("cursor") ?? ""}`;
      const reply = lists[key];
      if (typeof reply === "function") return (reply as () => Promise<Response>)();
      if (reply) return Promise.resolve(jsonResponse(reply));
    }
    const id = decodeURIComponent(url.pathname.replace("/api/jobs/", ""));
    if (details[id]) return Promise.resolve(jsonResponse(details[id]));
    return Promise.resolve(jsonResponse({ detail: { code: "not_found", message: "nf", details: {} } }, 404));
  };
}

const listCalls = (mockFetch: ReturnType<typeof vi.fn>) =>
  mockFetch.mock.calls.filter((c) => requestedUrl(c).pathname === "/api/jobs");

describe("JobsPage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    jobStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
  });

  it("filters by status server-side via the status dropdown", async () => {
    mockFetch.mockImplementation(
      routeFetch({
        "|": { items: [job("job_a"), job("job_b")], next_cursor: null },
        "FAILED|": { items: [job("job_failed", { status: "FAILED" })], next_cursor: null },
      }),
    );

    render(<JobsPage />);
    expect(await screen.findByText("job_a")).toBeTruthy();
    expect(requestedUrl(listCalls(mockFetch)[0]).searchParams.get("status")).toBeNull();

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "FAILED" } });

    expect(await screen.findByText("job_failed")).toBeTruthy();
    const url = requestedUrl(listCalls(mockFetch)[1]);
    expect(url.pathname).toBe("/api/jobs");
    expect(url.searchParams.get("status")).toBe("FAILED");
    expect(screen.queryByText("job_a")).toBeNull();
  });

  it("shows each job's source and target languages", async () => {
    mockFetch.mockImplementation(
      routeFetch({ "|": { items: [job("job_a")], next_cursor: null } }, { job_a: detail("job_a", "en", ["es", "de"]) }),
    );

    render(<JobsPage />);
    expect(await screen.findByText("EN")).toBeTruthy();
    expect(screen.getByText("ES, DE")).toBeTruthy();
  });

  it("filters the visible list by keyword without another list request", async () => {
    mockFetch.mockImplementation(
      routeFetch({
        "|": {
          items: [job("job_alpha"), job("job_beta", { stage: "localization" }), job("job_gamma")],
          next_cursor: null,
        },
      }),
    );

    render(<JobsPage />);
    expect(await screen.findByText("job_alpha")).toBeTruthy();

    const search = screen.getByRole("searchbox", { name: "Search" });
    fireEvent.change(search, { target: { value: "ALPHA" } });
    expect(screen.getByText("job_alpha")).toBeTruthy();
    expect(screen.queryByText("job_beta")).toBeNull();
    expect(screen.queryByText("job_gamma")).toBeNull();

    fireEvent.change(search, { target: { value: "localiz" } });
    expect(screen.getByText("job_beta")).toBeTruthy();
    expect(screen.queryByText("job_alpha")).toBeNull();

    fireEvent.change(search, { target: { value: "nothing-here" } });
    expect(screen.getByText("No jobs match the current filter.")).toBeTruthy();

    expect(listCalls(mockFetch)).toHaveLength(1);
  });

  it("matches the keyword against the Hooks of each job's Clips", async () => {
    mockFetch.mockImplementation(
      routeFetch(
        { "|": { items: [job("job_a"), job("job_b")], next_cursor: null } },
        {
          job_a: detail("job_a", "en", ["es"], ["Why 90% of B2B SaaS Ads Fail"]),
          job_b: detail("job_b", "en", ["es"], ["Pricing is a product decision"]),
        },
      ),
    );

    render(<JobsPage />);
    await screen.findByText("job_a");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), { target: { value: "saas ads" } });

    await waitFor(() => expect(screen.queryByText("job_b")).toBeNull());
    expect(screen.getByText("job_a")).toBeTruthy();
  });

  it("loads the next page via next_cursor, keeping the status filter and appending results", async () => {
    mockFetch.mockImplementation(
      routeFetch({
        "|": { items: [job("job_1")], next_cursor: null },
        "PROCESSING|": { items: [job("job_p1", { status: "PROCESSING" })], next_cursor: "cur_2" },
        "PROCESSING|cur_2": { items: [job("job_p2", { status: "PROCESSING" })], next_cursor: null },
      }),
    );

    render(<JobsPage />);
    expect(await screen.findByText("job_1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "PROCESSING" } });
    expect(await screen.findByText("job_p1")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("job_p2")).toBeTruthy();
    expect(screen.getByText("job_p1")).toBeTruthy();
    const url = requestedUrl(listCalls(mockFetch)[2]);
    expect(url.pathname).toBe("/api/jobs");
    expect(url.searchParams.get("cursor")).toBe("cur_2");
    expect(url.searchParams.get("status")).toBe("PROCESSING");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Load more" })).toBeNull());
  });

  it("drops a 'load more' page that arrives after the status filter changed", async () => {
    let releaseMore!: () => void;
    const lateMore = new Promise<Response>((resolve) => {
      releaseMore = () =>
        resolve(jsonResponse({ items: [job("job_p2", { status: "PROCESSING" })], next_cursor: null }));
    });
    mockFetch.mockImplementation(
      routeFetch({
        "PROCESSING|": { items: [job("job_p1", { status: "PROCESSING" })], next_cursor: "cur_2" },
        "PROCESSING|cur_2": () => lateMore,
        "FAILED|": { items: [job("job_f1", { status: "FAILED" })], next_cursor: null },
        "|": { items: [], next_cursor: null },
      }),
    );

    render(<JobsPage />);
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "PROCESSING" } });
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "FAILED" } });
    expect(await screen.findByText("job_f1")).toBeTruthy();

    releaseMore();
    await lateMore;
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("job_p2")).toBeNull();
    expect(screen.queryByText("job_p1")).toBeNull();
  });
});
