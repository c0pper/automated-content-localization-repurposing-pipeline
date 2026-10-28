import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { JobDetailPage } from "@/pages/JobDetailPage";
import { jobStore, profileStore } from "@/store";
import type { Job } from "@/lib/types";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    job_id: "job_42",
    status: "COMPLETED",
    stage: "delivery",
    source: { type: "url", url: "https://example.com/raw.mp4" },
    source_language: { code: "en", origin: "detected", detected_code: "en" },
    target_languages: ["es", "de"],
    lip_sync: false,
    parent_job_id: null,
    derived_mode: null,
    created_at: "2026-10-27T10:00:00Z",
    updated_at: "2026-10-27T11:00:00Z",
    expires_at: null,
    review_url: "http://localhost:8000/api/review/tok_abc",
    segments: [
      {
        segment_id: 7,
        start_time: "00:02:14",
        end_time: "00:03:05",
        hook_title: "Why 90% of B2B SaaS Ads Fail",
        caption: "Stop wasting budget on broad audiences...",
        selection_score: 87,
        score_breakdown: {
          hook_strength: 31,
          standalone_clarity: 22,
          emotional_payoff: 18,
          business_fit: 16,
        },
        rationale: "Contrarian opener with a clear payoff.",
        video_asset_url: "http://silo.local/bucket/jobs/job_42/base_7.mp4",
        localized_assets: { es: "http://silo.local/bucket/jobs/job_42/clip_7_es.mp4" },
        localized_copy: {
          es: {
            hook_title: "Por qué fallan el 90% de los anuncios B2B SaaS",
            caption: "Deja de gastar presupuesto en audiencias amplias...",
          },
        },
      },
    ],
    content: { linkedin_post: "LinkedIn breakdown text", newsletter: "Newsletter draft text" },
    copy_origin: {
      planning_model: "openrouter/anthropic/claude-3.5-sonnet",
      copy_model: "openrouter/anthropic/claude-3.5-sonnet",
      translation_model: "openrouter/openai/gpt-4o-mini",
      source_language: "en",
    },
    selection: {
      segment_ids: [7],
      languages: ["es"],
      expected_total_usd: "1.250000",
      confirmed_at: "2026-10-27T10:30:00Z",
    },
    cost: {
      job_budget_usd: "25.00",
      spent_usd: "3.40",
      workspace_remaining_usd: "471.60",
      projected_localization_usd: null,
    },
    error: null,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("JobDetailPage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    // Any call not explicitly mocked (e.g. workspace) resolves to an empty 404.
    mockFetch.mockResolvedValue(
      jsonResponse({ detail: { code: "not_found", message: "nope", details: {} } }, 404),
    );
    jobStore.getState().reset();
    profileStore.setState({ workspace: null, loading: false, error: null, notice: null });
  });

  afterEach(() => {
    cleanup();
  });

  it("loads GET /api/jobs/{id} and shows every clip field from the wire schema", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob()));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/api/jobs/job_42"));
    expect(init).toMatchObject({ method: "GET", credentials: "include" });

    const c = within(card);
    expect(c.getByText("Segment 7")).toBeTruthy();
    expect(c.getByText("00:02:14 – 00:03:05")).toBeTruthy();
    expect(c.getByText("Why 90% of B2B SaaS Ads Fail")).toBeTruthy();
    expect(c.getByText("Stop wasting budget on broad audiences...")).toBeTruthy();
    expect(c.getByText("Contrarian opener with a clear payoff.")).toBeTruthy();
    expect(card.textContent).toContain("Selection score: 87");
    expect(card.textContent).toContain("Hook strength: 31");
    expect(card.textContent).toContain("Standalone clarity: 22");
    expect(card.textContent).toContain("Emotional payoff: 18");
    expect(card.textContent).toContain("Business fit: 16");
  });

  it("links clip assets through the stable /api/jobs/{id}/assets redirect routes, never raw store URLs", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob()));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const c = within(card);
    const base = c.getByRole("link", { name: /Base clip/ });
    expect(base.getAttribute("href")).toBe("/api/jobs/job_42/assets/base_7");
    const es = c.getByRole("link", { name: /Localized clip \(es\)/ });
    expect(es.getAttribute("href")).toBe("/api/jobs/job_42/assets/clip_7_es");
    expect(card.innerHTML).not.toContain("silo.local");
  });

  it("shows that no localized clips exist yet before localization", async () => {
    const job = makeJob({ status: "PROCESSING", stage: "rendering", selection: null });
    job.segments[0].localized_assets = {};
    job.segments[0].localized_copy = {};
    job.segments[0].video_asset_url = null as unknown as string;
    mockFetch.mockResolvedValueOnce(jsonResponse(job));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const c = within(card);
    expect(c.queryByRole("link", { name: /Base clip/ })).toBeNull();
    expect(c.getByText("No localized clips yet")).toBeTruthy();
  });

  it("shows localized Hook and caption per Target Language and long-form copy in the Source Language", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob()));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const copy = within(within(card).getByRole("group", { name: "Localized copy (es)" }));
    expect(copy.getByText("Por qué fallan el 90% de los anuncios B2B SaaS")).toBeTruthy();
    expect(copy.getByText("Deja de gastar presupuesto en audiencias amplias...")).toBeTruthy();

    expect(screen.getByText("LinkedIn breakdown text")).toBeTruthy();
    expect(screen.getByText("Newsletter draft text")).toBeTruthy();
  });

  it("shows status, cost summary and the confirmed selection without asking for the gate", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob()));
    render(<JobDetailPage jobId="job_42" />);

    const costs = await screen.findByRole("region", { name: "Costs" });
    expect(costs.textContent).toContain("Job budget");
    expect(costs.textContent).toContain("25.00");
    expect(costs.textContent).toContain("Spent");
    expect(costs.textContent).toContain("3.40");
    expect(costs.textContent).toContain("Workspace remaining");
    expect(costs.textContent).toContain("471.60");

    const selection = screen.getByRole("region", { name: "Selection" });
    expect(selection.textContent).toMatch(/Clips:?\s*7/);
    expect(selection.textContent).toMatch(/Languages:?\s*es/);
    expect(selection.textContent).toMatch(/Confirmed total:?\s*1\.250000/);

    expect(screen.getByText("COMPLETED")).toBeTruthy();
    expect(mockFetch.mock.calls.some(([u]) => String(u).includes("/selection"))).toBe(false);
  });

  it("shows that nothing is selected yet and shows the job error for a failed job", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        makeJob({
          status: "FAILED",
          selection: null,
          error: { code: "voice_profile_missing", message: "No voice profile", retryable: true },
        }),
      ),
    );
    render(<JobDetailPage jobId="job_42" />);

    const selection = await screen.findByRole("region", { name: "Selection" });
    expect(selection.textContent).toContain("None selected yet");
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("voice_profile_missing");
  });

  it("loads the gate for a job awaiting selection and labels the clip column", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(makeJob({ status: "AWAITING_SELECTION", stage: "selection", selection: null })),
    );
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        job_id: "job_42",
        status: "AWAITING_SELECTION",
        expires_at: null,
        source_language: null,
        target_languages: ["es", "de"],
        lip_sync: false,
        segments: [],
        cost_matrix: [],
        projected_total_usd: "2.500000",
      }),
    );
    render(<JobDetailPage jobId="job_42" />);

    expect(await screen.findByText("2.500000")).toBeTruthy();
    expect(mockFetch.mock.calls[1][0]).toEqual(expect.stringContaining("/api/jobs/job_42/selection"));
    expect(screen.getByRole("columnheader", { name: "Segment" })).toBeTruthy();
  });

  it("shows a not-found message when the job does not exist", async () => {
    render(<JobDetailPage jobId="job_missing" />);
    expect(await screen.findByText("Job not found.")).toBeTruthy();
  });
});
