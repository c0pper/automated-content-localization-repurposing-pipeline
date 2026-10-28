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

  it("plays Base and Localized Clips through the stable /api/jobs/{id}/assets redirect routes, never raw store URLs", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob()));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const c = within(card);
    const base = c.getByLabelText("Base clip");
    expect(base.tagName).toBe("VIDEO");
    expect(base.getAttribute("src")).toBe("/api/jobs/job_42/assets/base_7");
    expect(c.getByText("Captions burned in (en)")).toBeTruthy();
    const es = c.getByLabelText("Localized clip (es)");
    expect(es.tagName).toBe("VIDEO");
    expect(es.getAttribute("src")).toBe("/api/jobs/job_42/assets/clip_7_es");
    expect(c.getByText("Captions burned in (es)")).toBeTruthy();
    expect(c.getByRole("link", { name: "Open Localized clip (es)" }).getAttribute("href")).toBe(
      "/api/jobs/job_42/assets/clip_7_es",
    );
    expect(card.innerHTML).not.toContain("silo.local");
  });

  it("only offers localized playback for languages whose localized clip is available", async () => {
    // de is a Target Language but was not localized (no asset in the job view).
    const job = makeJob();
    job.segments[0].localized_assets = { es: "http://silo.local/bucket/clip_7_es.mp4", de: "" };
    mockFetch.mockResolvedValueOnce(jsonResponse(job));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const c = within(card);
    expect(c.getByLabelText("Localized clip (es)")).toBeTruthy();
    expect(c.queryByLabelText("Localized clip (de)")).toBeNull();
    expect(card.innerHTML).not.toContain("clip_7_de");
  });

  it("shows the localized Hook and social caption below each localized clip, noting the Voice Profile and lip-sync", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob({ lip_sync: true })));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const video = within(card).getByLabelText("Localized clip (es)");
    const copy = within(card).getByRole("group", { name: "Localized copy (es)" });
    expect(video.compareDocumentPosition(copy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(copy.getAttribute("lang")).toBe("es");
    expect(within(copy).getByText("Por qué fallan el 90% de los anuncios B2B SaaS")).toBeTruthy();
    expect(card.textContent).toContain("Dubbed with your Voice Profile");
    expect(card.textContent).toContain("lip-sync applied");
  });

  it("does not claim lip-sync when the job was submitted without it", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob({ lip_sync: false })));
    render(<JobDetailPage jobId="job_42" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    expect(card.textContent).toContain("Dubbed with your Voice Profile");
    expect(card.textContent).not.toContain("lip-sync applied");
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
    expect(c.queryByLabelText("Base clip")).toBeNull();
    expect(card.querySelector("video")).toBeNull();
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

  it("explains a lip-sync failure on a failed job without implying a fallback", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        makeJob({
          status: "FAILED",
          lip_sync: true,
          error: {
            code: "lip_sync_unavailable",
            message: "Lip-sync was requested but no lip-sync provider is configured",
            retryable: true,
          },
        }),
      ),
    );
    render(<JobDetailPage jobId="job_42" />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "Lip-sync failed, so the whole job stopped. No clips were delivered without lip-sync.",
    );
    expect(alert.textContent).toContain("lip_sync_unavailable");
  });

  it("explains a missing caption alignment from the speech provider on a failed job", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        makeJob({
          status: "FAILED",
          error: {
            code: "caption_alignment_unavailable",
            message: "The speech provider returned no caption alignment",
            retryable: true,
          },
        }),
      ),
    );
    render(<JobDetailPage jobId="job_42" />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "The speech provider returned no caption timing, so the whole job stopped. No clips were delivered without captions.",
    );
  });

  it("links a job awaiting selection to its Selection Gate page", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(makeJob({ status: "AWAITING_SELECTION", stage: "selection", selection: null })),
    );
    render(<JobDetailPage jobId="job_42" />);

    const link = await screen.findByRole("link", { name: "Open Selection Gate" });
    expect(link.getAttribute("href")).toBe("#/jobs/job_42/localization");
    expect(screen.getByRole("region", { name: "Selection Gate" }).textContent).toContain(
      "waiting for you to choose",
    );
  });

  it("does not offer the Selection Gate once the job has moved on", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeJob()));
    render(<JobDetailPage jobId="job_42" />);
    await screen.findByRole("article", { name: "Segment 7" });
    expect(screen.queryByRole("link", { name: "Open Selection Gate" })).toBeNull();
  });

  it("shows a not-found message when the job does not exist", async () => {
    render(<JobDetailPage jobId="job_missing" />);
    expect(await screen.findByText("Job not found.")).toBeTruthy();
  });
});
