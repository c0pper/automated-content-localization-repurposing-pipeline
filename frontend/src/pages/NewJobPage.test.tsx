import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NewJobPage } from "@/pages/NewJobPage";
import { jobStore, profileStore } from "@/store";
import type { WorkspaceSettings } from "@/lib/types";

const workspace: WorkspaceSettings = {
  workspace_id: "ws_test",
  target_language_allowlist: ["en", "es", "de"],
  default_models: {
    planning: "openrouter/anthropic/claude-3.5-sonnet",
    copy: "openrouter/anthropic/claude-3.5-sonnet",
    translation: "openrouter/openai/gpt-4o-mini",
  },
  job_budget_usd: "50.00",
  monthly_budget_usd: "500.00",
  max_concurrent_jobs: 3,
  current_month_spend_usd: "10.00",
  remaining_usd: "490.00",
  voice_profile: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("NewJobPage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    profileStore.setState({ workspace: null, loading: false, error: null, notice: null });
    jobStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
  });

  it("loads workspace defaults and preselects them in a curated dropdown per task", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    render(<NewJobPage onCreated={() => {}} />);

    const planning = (await screen.findByLabelText("Planning model")) as HTMLSelectElement;
    const copy = screen.getByLabelText("Copy model") as HTMLSelectElement;
    const translation = screen.getByLabelText("Translation model") as HTMLSelectElement;

    expect(mockFetch.mock.calls[0][0]).toEqual(expect.stringContaining("/api/workspace"));
    expect(planning.value).toBe("openrouter/anthropic/claude-3.5-sonnet");
    expect(copy.value).toBe("openrouter/anthropic/claude-3.5-sonnet");
    expect(translation.value).toBe("openrouter/openai/gpt-4o-mini");
    expect(Array.from(translation.options).map((o) => o.value)).toEqual([
      "openrouter/anthropic/claude-3.5-sonnet",
      "openrouter/openai/gpt-4o-mini",
      "openrouter/google/gemini-1.5-flash",
    ]);
    expect(Array.from(planning.options).map((o) => o.value)).toContain(
      "openrouter/google/gemini-1.5-pro",
    );
  });

  it("submits POST /api/jobs with an Idempotency-Key and only the changed model overrides", async () => {
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ job_id: "job_1", status: "RECEIVED", created_at: "2026-10-28T00:00:00Z" }, 202),
    );
    render(<NewJobPage onCreated={onCreated} />);

    const translation = await screen.findByLabelText("Translation model");
    fireEvent.change(screen.getByLabelText("Video URL"), {
      target: { value: "https://example.com/talk.mp4" },
    });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(screen.getByLabelText("de"));
    fireEvent.change(translation, { target: { value: "openrouter/google/gemini-1.5-flash" } });
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job_1"));
    const [url, init] = mockFetch.mock.calls[1];
    expect(url).toEqual(expect.stringContaining("/api/jobs"));
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(init.body)).toEqual({
      source: { type: "url", url: "https://example.com/talk.mp4" },
      target_languages: ["es", "de"],
      lip_sync: false,
      model_overrides: { translation: "openrouter/google/gemini-1.5-flash" },
    });
  });

  it("shows a user-facing message when the backend rejects a model with 422 invalid_model", async () => {
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        { detail: { code: "invalid_model", message: "Model x is not allowed for planning", details: {} } },
        422,
      ),
    );
    render(<NewJobPage onCreated={onCreated} />);

    await screen.findByLabelText("Planning model");
    fireEvent.click(screen.getByLabelText("Silo object key"));
    fireEvent.change(screen.getByLabelText("Object key"), { target: { value: "uploads/talk.mp4" } });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "One of the selected models is not in the curated list. Pick another model and try again.",
    );
    expect(onCreated).not.toHaveBeenCalled();
    expect(JSON.parse(mockFetch.mock.calls[1][1].body).source).toEqual({
      type: "object",
      key: "uploads/talk.mp4",
    });
  });
});
