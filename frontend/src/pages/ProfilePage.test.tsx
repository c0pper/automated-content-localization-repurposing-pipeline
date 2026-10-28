import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProfilePage } from "@/pages/ProfilePage";
import { profileStore } from "@/store";
import type { WorkspaceSettings } from "@/lib/types";

const workspace: WorkspaceSettings = {
  workspace_id: "ws_test",
  target_language_allowlist: ["en", "es", "de"],
  default_models: { planning: "openai/gpt-4o", copy: "openai/gpt-4o-mini" },
  job_budget_usd: "50.00",
  monthly_budget_usd: "500.00",
  max_concurrent_jobs: 3,
  current_month_spend_usd: "10.00",
  remaining_usd: "490.00",
  voice_profile: {
    provider: "elevenlabs",
    voice_id: "voice_123",
    updated_at: "2026-10-27T00:00:00Z",
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockGetWorkspace(payload: WorkspaceSettings = workspace) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
    jsonResponse(payload),
  );
}

describe("ProfilePage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    profileStore.setState({
      workspace: null,
      loading: false,
      error: null,
      notice: null,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the workspace settings summary from GET /api/workspace", async () => {
    mockGetWorkspace();
    render(<ProfilePage />);

    expect(await screen.findByText("ws_test")).toBeTruthy();
    expect(screen.getByText("en, es, de")).toBeTruthy();
    expect(screen.getAllByText("$50.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$500.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$10.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$490.00").length).toBeGreaterThan(0);
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("openai/gpt-4o")).toBeTruthy();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/workspace"),
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("shows a configured voice profile and can delete it", async () => {
    mockGetWorkspace();
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));

    render(<ProfilePage />);
    expect(await screen.findByText("voice_123")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Delete voice profile" }));

    await waitFor(() => {
      expect(profileStore.getState().workspace?.voice_profile).toBeNull();
    });
    expect(screen.getByRole("status").textContent).toContain(
      "Voice profile deleted.",
    );
    expect(
      screen.getByText(/No voice profile configured/),
    ).toBeTruthy();
  });

  it("saves a new voice profile through PUT /api/workspace/voice-profile", async () => {
    mockGetWorkspace({ ...workspace, voice_profile: null });
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        voice_profile: {
          provider: "elevenlabs",
          voice_id: "voice_new",
          updated_at: "2026-10-28T00:00:00Z",
        },
      }),
    );

    render(<ProfilePage />);
    await screen.findByText(/No voice profile configured/);

    fireEvent.change(screen.getByLabelText("Voice ID"), {
      target: { value: "voice_new" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save voice profile" }));

    expect(await screen.findByText("voice_new")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain(
      "Voice profile updated.",
    );

    const putCall = mockFetch.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
    );
    expect(putCall?.[0]).toContain("/api/workspace/voice-profile");
    expect(JSON.parse(String((putCall?.[1] as RequestInit).body))).toEqual({
      provider: "elevenlabs",
      voice_id: "voice_new",
    });
  });

  it("exposes the API key rotation placeholder workflow", async () => {
    mockGetWorkspace();
    render(<ProfilePage />);
    await screen.findByText("ws_test");

    fireEvent.click(
      screen.getByRole("button", { name: "Rotate API key (placeholder)" }),
    );
    expect(screen.getByRole("status").textContent).toContain(
      "Placeholder rotation triggered",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Clear key (placeholder)" }),
    );
    expect(screen.getByRole("status").textContent).toContain(
      "Placeholder clear triggered",
    );
  });

  it("links the summary to voice profile management", async () => {
    mockGetWorkspace();
    render(<ProfilePage />);
    await screen.findByText("ws_test");

    fireEvent.click(screen.getByRole("button", { name: "Manage voice profile" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Voice ID"));
  });
});
