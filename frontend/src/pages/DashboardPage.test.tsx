import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { DashboardPage } from "@/pages/DashboardPage";
import { jobStore } from "@/store";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function summary(job_id: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    job_id,
    status,
    stage: null,
    created_at: "2026-10-27T14:05:00Z",
    expires_at: null,
    review_url: null,
    ...extra,
  };
}

function detail(job_id: string, source: string | null, targets: string[]) {
  return {
    job_id,
    status: "COMPLETED",
    stage: null,
    source_language: source ? { code: source, origin: "detected", detected_code: source } : null,
    target_languages: targets,
    segments: [],
  };
}

/** Routes mocked fetch calls by URL so parallel detail requests resolve independently. */
function routeFetch(routes: Record<string, unknown>) {
  return (input: RequestInfo | URL) => {
    const url = String(input);
    const path = new URL(url, "http://localhost").pathname;
    const query = new URL(url, "http://localhost").search;
    const key = Object.keys(routes).find((k) => {
      const [p, q] = k.split("?");
      return path === p && (q === undefined || query.includes(q));
    });
    if (!key) return Promise.resolve(jsonResponse({ detail: { code: "not_found", message: "nf", details: {} } }, 404));
    return Promise.resolve(jsonResponse(routes[key]));
  };
}

function card(jobId: string): HTMLElement {
  return screen.getByText(jobId).closest("article") as HTMLElement;
}

describe("DashboardPage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    jobStore.getState().reset();
  });

  afterEach(() => cleanup());

  it("shows each job's status, stage, created date and source/target languages", async () => {
    mockFetch.mockImplementation(
      routeFetch({
        "/api/jobs": {
          items: [summary("job_a", "PROCESSING", { stage: "localization" })],
          next_cursor: null,
        },
        "/api/jobs/job_a": detail("job_a", "en", ["es", "de"]),
      }),
    );

    render(<DashboardPage />);

    await screen.findByText("job_a");
    const c = card("job_a");
    expect(within(c).getByText("Processing")).toBeTruthy();
    expect(within(c).getByText("localization")).toBeTruthy();
    expect(within(c).getByText("2026-10-27 14:05 UTC")).toBeTruthy();
    expect(await within(c).findByText("EN")).toBeTruthy();
    expect(within(c).getByText("ES, DE")).toBeTruthy();
  });

  it("offers a quick review link only for COMPLETED jobs", async () => {
    const reviewUrl = "http://localhost:8000/api/review/tok_done";
    mockFetch.mockImplementation(
      routeFetch({
        "/api/jobs": {
          items: [
            summary("job_done", "COMPLETED", { review_url: reviewUrl }),
            // Partial jobs can already carry a review token; the dashboard must not offer it.
            summary("job_partial", "AWAITING_SELECTION", {
              review_url: "http://localhost:8000/api/review/tok_partial",
            }),
            summary("job_failed", "FAILED", {
              review_url: "http://localhost:8000/api/review/tok_failed",
            }),
          ],
          next_cursor: null,
        },
      }),
    );

    render(<DashboardPage />);

    await screen.findByText("job_done");
    const link = within(card("job_done")).getByRole("link", { name: "Open review" });
    expect(link.getAttribute("href")).toBe(reviewUrl);
    expect(within(card("job_partial")).queryByRole("link", { name: "Open review" })).toBeNull();
    expect(within(card("job_failed")).queryByRole("link", { name: "Open review" })).toBeNull();
    expect(screen.queryByText(/tok_partial|tok_failed/)).toBeNull();
  });

  it("pages through /api/jobs with the cursor, keeping earlier jobs listed", async () => {
    mockFetch.mockImplementation(
      routeFetch({
        // more specific route first: the second page
        "/api/jobs?cursor=cur_1": { items: [summary("job_old", "COMPLETED")], next_cursor: null },
        "/api/jobs": { items: [summary("job_new", "RECEIVED")], next_cursor: "cur_1" },
      }),
    );

    render(<DashboardPage />);

    await screen.findByText("job_new");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    await screen.findByText("job_old");
    expect(screen.getByText("job_new")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();

    const listCalls = mockFetch.mock.calls
      .map(([url]) => new URL(String(url), "http://localhost"))
      .filter((u) => u.pathname === "/api/jobs");
    expect(listCalls).toHaveLength(2);
    expect(listCalls[0].searchParams.get("cursor")).toBeNull();
    expect(listCalls[1].searchParams.get("cursor")).toBe("cur_1");
  });
});
