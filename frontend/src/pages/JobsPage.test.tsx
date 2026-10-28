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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestedUrl(call: unknown[]): URL {
  return new URL(String(call[0]), "http://localhost");
}

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
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [job("job_a"), job("job_b")], next_cursor: null }));
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ items: [job("job_failed", { status: "FAILED" })], next_cursor: null }),
    );

    render(<JobsPage />);
    expect(await screen.findByText("job_a")).toBeTruthy();
    expect(requestedUrl(mockFetch.mock.calls[0]).searchParams.get("status")).toBeNull();

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "FAILED" } });

    expect(await screen.findByText("job_failed")).toBeTruthy();
    const url = requestedUrl(mockFetch.mock.calls[1]);
    expect(url.pathname).toBe("/api/jobs");
    expect(url.searchParams.get("status")).toBe("FAILED");
    expect(screen.queryByText("job_a")).toBeNull();
  });

  it("filters the visible list by keyword without another request", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        items: [job("job_alpha"), job("job_beta", { stage: "localization" }), job("job_gamma")],
        next_cursor: null,
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

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("loads the next page via next_cursor, keeping the status filter and appending results", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [job("job_1")], next_cursor: null }));
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ items: [job("job_p1", { status: "PROCESSING" })], next_cursor: "cur_2" }),
    );
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ items: [job("job_p2", { status: "PROCESSING" })], next_cursor: null }),
    );

    render(<JobsPage />);
    expect(await screen.findByText("job_1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "PROCESSING" } });
    expect(await screen.findByText("job_p1")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("job_p2")).toBeTruthy();
    expect(screen.getByText("job_p1")).toBeTruthy();
    const url = requestedUrl(mockFetch.mock.calls[2]);
    expect(url.pathname).toBe("/api/jobs");
    expect(url.searchParams.get("cursor")).toBe("cur_2");
    expect(url.searchParams.get("status")).toBe("PROCESSING");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Load more" })).toBeNull());
  });
});
