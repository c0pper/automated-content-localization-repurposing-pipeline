import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ReviewPage } from "@/pages/ReviewPage";
import type { ReviewManifest } from "@/lib/types";

const BASE = "http://localhost:8000/api/review/tok_abc/assets";

function makeManifest(overrides: Partial<ReviewManifest> = {}): ReviewManifest {
  return {
    job_id: "job_42",
    status: "FAILED",
    created_at: "2026-10-27T10:00:00Z",
    source_language: { code: "en", origin: "detected", detected_code: "en" },
    target_languages: ["es"],
    lip_sync: false,
    segments: [
      {
        segment_id: 7,
        hook_title: "Why 90% of B2B SaaS Ads Fail",
        caption: "Stop wasting budget on broad audiences...",
        video_asset_url: `${BASE}/base_7`,
        localized_assets: { es: `${BASE}/clip_7_es` },
        localized_copy: {
          es: { hook_title: "Por qué fallan los anuncios", caption: "Deja de gastar presupuesto..." },
        },
      },
      {
        segment_id: 8,
        hook_title: "Second hook",
        caption: "Second caption",
        video_asset_url: null,
        localized_assets: {},
        localized_copy: {},
      },
    ],
    content: { linkedin_post: "LinkedIn breakdown text", newsletter: "Newsletter draft text" },
    copy_origin: null,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ReviewPage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("loads GET /api/review/{token} and plays available assets through the review redirect routes, even for a failed Job", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeManifest()));
    render(<ReviewPage token="tok_abc" />);

    const card = await screen.findByRole("article", { name: "Segment 7" });
    const [url] = mockFetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/api/review/tok_abc"));
    expect(screen.getByText("FAILED")).toBeTruthy();

    const c = within(card);
    expect(c.getByText("Why 90% of B2B SaaS Ads Fail")).toBeTruthy();
    expect(c.getByLabelText("Base clip").getAttribute("src")).toBe("/api/review/tok_abc/assets/base_7");
    expect(c.getByLabelText("Localized clip (es)").getAttribute("src")).toBe(
      "/api/review/tok_abc/assets/clip_7_es",
    );
    expect(c.getByText("Por qué fallan los anuncios")).toBeTruthy();

    // A Clip without rendered assets is still listed, just without players.
    const partial = screen.getByRole("article", { name: "Segment 8" });
    expect(partial.querySelector("video")).toBeNull();
    expect(screen.getByText("LinkedIn breakdown text")).toBeTruthy();
  });

  it("does not offer Creator controls on the read-only review view", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeManifest({ status: "COMPLETED" })));
    render(<ReviewPage token="tok_abc" />);

    await screen.findByRole("article", { name: "Segment 7" });
    expect(screen.queryByRole("button", { name: /rotate|revoke/i })).toBeNull();
  });

  it("shows a revoked / not found state when the token 404s", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ detail: { code: "not_found", message: "Not found", details: {} } }, 404),
    );
    render(<ReviewPage token="tok_old" />);

    expect(await screen.findByText("This review link was revoked or does not exist.")).toBeTruthy();
    expect(document.querySelector("video")).toBeNull();
  });
});
