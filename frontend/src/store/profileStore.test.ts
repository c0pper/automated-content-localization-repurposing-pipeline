import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createProfileStore } from "@/store/profileStore";
import type { WorkspaceSettings } from "@/lib/types";

const workspace: WorkspaceSettings = {
  workspace_id: "ws_test",
  target_language_allowlist: ["en", "es"],
  default_models: {},
  job_budget_usd: "50.00",
  monthly_budget_usd: "500.00",
  max_concurrent_jobs: 2,
  current_month_spend_usd: "0.00",
  remaining_usd: "500.00",
  voice_profile: null,
};

describe("profile store", () => {
  let store: ReturnType<typeof createProfileStore>;
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    store = createProfileStore();
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("loads workspace successfully", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(workspace), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await store.getState().loadWorkspace();
    expect(store.getState().workspace?.workspace_id).toBe("ws_test");
    expect(store.getState().workspace?.job_budget_usd).toBe("50.00");
    expect(store.getState().workspace?.voice_profile).toBeNull();
  });

  it("sets voice profile", async () => {
    store.setState({ workspace });
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          voice_profile: {
            provider: "elevenlabs",
            voice_id: "voice_123",
            updated_at: "2026-10-27T00:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await store.getState().setVoiceProfile("elevenlabs", "voice_123");
    expect(store.getState().workspace?.voice_profile).toEqual({
      provider: "elevenlabs",
      voice_id: "voice_123",
      updated_at: "2026-10-27T00:00:00Z",
    });
    expect(store.getState().notice).toBe("voiceProfileUpdated");
  });

  it("deletes voice profile", async () => {
    store.setState({
      workspace: {
        ...workspace,
        voice_profile: {
          provider: "elevenlabs",
          voice_id: "voice_123",
          updated_at: "2026-10-27T00:00:00Z",
        },
      },
    });
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await store.getState().deleteVoiceProfile();
    expect(store.getState().workspace?.voice_profile).toBeNull();
    expect(store.getState().notice).toBe("voiceProfileDeleted");
  });

  it("rotates API key placeholder without touching the network", () => {
    store.getState().rotateApiKeyPlaceholder();
    expect(store.getState().notice).toBe("apiKeyRotationPlaceholder");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
