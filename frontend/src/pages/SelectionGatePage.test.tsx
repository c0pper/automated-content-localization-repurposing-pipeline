import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { SelectionGatePage } from "@/pages/SelectionGatePage";
import { jobStore } from "@/store";
import type { GatePayload } from "@/lib/types";

function seg(segment_id: number, hook_title: string) {
  return {
    segment_id,
    start_time: "00:00:10",
    end_time: "00:00:40",
    hook_title,
    caption: `caption ${segment_id}`,
    selection_score: 80,
    score_breakdown: { hook_strength: 30, standalone_clarity: 20, emotional_payoff: 15, business_fit: 15 },
    rationale: "because",
    base_asset_url: `http://localhost:8000/api/jobs/job_42/assets/base_${segment_id}`,
  };
}

function cell(segment_id: number, language: string, t: string, v: string, l: string, total: string) {
  return { segment_id, language, translation_usd: t, voice_usd: v, lip_sync_usd: l, total_usd: total };
}

function makeGate(overrides: Partial<GatePayload> = {}): GatePayload {
  return {
    job_id: "job_42",
    status: "AWAITING_SELECTION",
    expires_at: "2026-10-30T10:00:00+00:00",
    source_language: { code: "en", origin: "detected", detected_code: "en" },
    target_languages: ["es", "de"],
    lip_sync: false,
    segments: [seg(1, "Hook one"), seg(2, "Hook two"), seg(3, "Hook three")],
    cost_matrix: [
      cell(1, "es", "0.10", "0.20", "0.00", "0.30"),
      cell(1, "de", "0.10", "0.25", "0.00", "0.35"),
      cell(2, "es", "0.05", "0.100001", "0.00", "0.150001"),
      cell(2, "de", "0.05", "0.15", "0.00", "0.20"),
      cell(3, "es", "0.20", "0.40", "0.00", "0.60"),
      cell(3, "de", "0.20", "0.45", "0.00", "0.65"),
    ],
    projected_total_usd: "2.250001",
    ...overrides,
  } as GatePayload;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, details: Record<string, unknown> = {}): Response {
  return jsonResponse({ detail: { code, message: "server message", details } }, status);
}

function selectionPosts(mockFetch: ReturnType<typeof vi.fn>) {
  return mockFetch.mock.calls.filter(
    ([u, init]) => String(u).includes("/api/jobs/job_42/selection") && init?.method === "POST",
  );
}

function jobAfterConfirm(stage: string, segment_ids: number[], languages: string[], total: string) {
  return {
    job_id: "job_42",
    status: "PROCESSING",
    stage,
    source: null,
    source_language: { code: "en", origin: "detected", detected_code: "en" },
    target_languages: ["es", "de"],
    lip_sync: false,
    parent_job_id: null,
    derived_mode: null,
    created_at: "2026-10-27T10:00:00Z",
    updated_at: "2026-10-27T11:00:00Z",
    expires_at: null,
    review_url: null,
    segments: [],
    content: null,
    copy_origin: null,
    selection: { segment_ids, languages, expected_total_usd: total, confirmed_at: "2026-10-27T11:00:00Z" },
    cost: null,
    error: null,
  };
}

describe("SelectionGatePage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    mockFetch.mockResolvedValue(errorResponse(404, "not_found"));
    jobStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
  });

  it("loads the gate and shows the translation/voice/total cost for every Clip × Language cell", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeGate()));
    render(<SelectionGatePage jobId="job_42" />);

    const table = await screen.findByRole("table", { name: "Cost matrix" });
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/api/jobs/job_42/selection"));
    expect(init).toMatchObject({ method: "GET", credentials: "include" });

    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(expect.arrayContaining(["Clip", "Language", "Translation", "Voice", "Total"]));
    expect(headers).not.toContain("Lip sync");

    const row = within(table).getByRole("row", { name: /Hook two.*de/ });
    expect(row.textContent).toContain("$0.05");
    expect(row.textContent).toContain("$0.15");
    expect(row.textContent).toContain("$0.20");
    // 3 clips × 2 languages + header row.
    expect(within(table).getAllByRole("row")).toHaveLength(7);
    expect(screen.getByText(/Projected total.*\$2\.250001/)).toBeTruthy();
  });

  it("shows a lip-sync column only when the Job was submitted with lip-sync", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        makeGate({
          lip_sync: true,
          segments: [seg(1, "Hook one")],
          target_languages: ["es"],
          cost_matrix: [cell(1, "es", "0.10", "0.20", "0.75", "1.05")],
          projected_total_usd: "1.05",
        }),
      ),
    );
    render(<SelectionGatePage jobId="job_42" />);

    const table = await screen.findByRole("table", { name: "Cost matrix" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toContain("Lip sync");
    expect(within(table).getByRole("row", { name: /Hook one.*es/ }).textContent).toContain("$0.75");
  });

  it("selects a rectangle of Clips × Languages and updates the exact total live", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeGate()));
    render(<SelectionGatePage jobId="job_42" />);
    await screen.findByRole("table", { name: "Cost matrix" });

    const total = () => screen.getByRole("status", { name: "Selected total" }).textContent;
    expect(total()).toBe("$0.00");
    expect(screen.getByText(/Nothing selected/)).toBeTruthy();

    fireEvent.click(screen.getByRole("checkbox", { name: "Clip 1: Hook one" }));
    // A Clip without a Language is not a rectangle: confirmation is blocked.
    expect(screen.getByText(/Select at least one Clip and one Language/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Confirm/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("checkbox", { name: "Clip 2: Hook two" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "es" }));
    // 0.30 + 0.150001
    expect(total()).toBe("$0.450001");
    fireEvent.click(screen.getByRole("checkbox", { name: "de" }));
    // + 0.35 + 0.20
    expect(total()).toBe("$1.000001");
    expect(screen.getByText("2 Clips × 2 Languages = 4 localized clips")).toBeTruthy();

    const table = screen.getByRole("table", { name: "Cost matrix" });
    expect(within(table).getByRole("row", { name: /Hook two.*de/ }).textContent).toContain("Selected");
    expect(within(table).getByRole("row", { name: /Hook three.*es/ }).textContent).toContain("Not selected");

    const confirm = screen.getByRole("button", { name: "Confirm selection for $1.000001" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(false);
  });
  it("integration: open gate → view matrix → select rectangle → confirm → Job is PROCESSING at stage localization", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeGate()));
    mockFetch.mockResolvedValueOnce(jsonResponse(jobAfterConfirm("localization", [1, 3], ["de"], "1.00"), 202));
    render(<SelectionGatePage jobId="job_42" />);

    const table = await screen.findByRole("table", { name: "Cost matrix" });
    expect(within(table).getAllByRole("row")).toHaveLength(7);

    fireEvent.click(screen.getByRole("checkbox", { name: "Clip 3: Hook three" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "de" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Clip 1: Hook one" }));
    // 0.35 + 0.65
    fireEvent.click(screen.getByRole("button", { name: "Confirm selection for $1.00" }));

    const status = await screen.findByText(/Selection confirmed/);
    expect(status.getAttribute("role")).toBe("status");
    expect(status.textContent).toContain("PROCESSING");
    expect(status.textContent).toContain("localization");

    const posts = selectionPosts(mockFetch);
    expect(posts).toHaveLength(1);
    const [, init] = posts[0];
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
    expect(new Headers(init.headers).get("Idempotency-Key")).toBeTruthy();
    // Clips and languages are sent in gate order, with the exact expected total.
    expect(JSON.parse(init.body)).toEqual({ segment_ids: [1, 3], languages: ["de"], expected_total_usd: "1.00" });
  });

  it("confirms the empty selection with a zero total so the Job completes without localization", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeGate()));
    mockFetch.mockResolvedValueOnce(jsonResponse(jobAfterConfirm("delivery", [], [], "0.00"), 202));
    render(<SelectionGatePage jobId="job_42" />);
    await screen.findByRole("table", { name: "Cost matrix" });

    fireEvent.click(screen.getByRole("button", { name: "Confirm without localization" }));

    const status = await screen.findByText(/Selection confirmed/);
    expect(status.textContent).toContain("delivery");
    const [, init] = selectionPosts(mockFetch)[0];
    expect(JSON.parse(init.body)).toEqual({ segment_ids: [], languages: [], expected_total_usd: "0.00" });
  });

  it("on 409 selection_price_changed shows the new total and requires a fresh confirmation", async () => {
    const repriced = makeGate({
      cost_matrix: makeGate().cost_matrix.map((c) =>
        c.segment_id === 1 && c.language === "es" ? { ...c, voice_usd: "0.30", total_usd: "0.40" } : c,
      ),
      projected_total_usd: "2.350001",
    });
    mockFetch.mockResolvedValueOnce(jsonResponse(makeGate()));
    mockFetch.mockResolvedValueOnce(
      errorResponse(409, "selection_price_changed", {
        current_total_usd: "0.40",
        cost_matrix: repriced.cost_matrix.map(({ segment_id, language, total_usd }) => ({ segment_id, language, total_usd })),
        projected_total_usd: "2.350001",
      }),
    );
    mockFetch.mockResolvedValueOnce(jsonResponse(repriced));
    render(<SelectionGatePage jobId="job_42" />);
    await screen.findByRole("table", { name: "Cost matrix" });

    fireEvent.click(screen.getByRole("checkbox", { name: "Clip 1: Hook one" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "es" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm selection for $0.30" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Prices changed");
    expect(alert.textContent).toContain("$0.40");
    // Not confirmed: still on the gate, with the new prices in the matrix and the total.
    expect(screen.queryByText(/Selection confirmed/)).toBeNull();
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "Selected total" }).textContent).toBe("$0.40"),
    );
    expect(within(screen.getByRole("table", { name: "Cost matrix" })).getByRole("row", { name: /Hook one.*es/ }).textContent).toContain("$0.40");
    expect(selectionPosts(mockFetch)).toHaveLength(1);

    mockFetch.mockResolvedValueOnce(jsonResponse(jobAfterConfirm("localization", [1], ["es"], "0.40"), 202));
    fireEvent.click(screen.getByRole("button", { name: "Confirm selection for $0.40" }));
    expect(await screen.findByText(/Selection confirmed/)).toBeTruthy();
    const posts = selectionPosts(mockFetch);
    expect(posts).toHaveLength(2);
    expect(JSON.parse(posts[1][1].body).expected_total_usd).toBe("0.40");
  });

  it("explains when the Job is not at the Selection Gate", async () => {
    mockFetch.mockResolvedValueOnce(errorResponse(409, "invalid_state"));
    render(<SelectionGatePage jobId="job_42" />);
    expect((await screen.findByRole("alert")).textContent).toBe("This Job is not at the Selection Gate.");
    expect(screen.getByRole("link", { name: "Back to job details" }).getAttribute("href")).toBe("#/jobs/job_42");
  });

  it("explains an expired gate", async () => {
    mockFetch.mockResolvedValueOnce(errorResponse(410, "selection_expired"));
    render(<SelectionGatePage jobId="job_42" />);
    expect((await screen.findByRole("alert")).textContent).toBe("The Selection Gate has expired.");
  });
});
