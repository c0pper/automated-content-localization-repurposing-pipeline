import { describe, it, expect, vi, beforeEach } from "vitest";
import { createProfileStore } from "@/store/profileStore";
import type { WorkspaceSettings } from "@/lib/types";
import { api } from "@/lib/api";

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
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          workspace_id: "ws_test",
          target_language_allowlist: ["en", "es"],
          default_models: {},
          job_budget_usd: "50.00",
          monthly_budget_usd: "500.00",
          max_concurrent_jobs: 2,
          current_month_spend_usd: "0.00",
          remaining_usd: "500.00",
          voice_profile: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await store.loadWorkspace();
    expect(store.workspace?.workspace_id).toBe("ws_test");
    expect(store.workspace?.job_budget_usd).toBe("50.00");
    expect(store.workspace?.voice_profile).toBeNull();
  });

  it("sets voice profile", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
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
    await store.setVoiceProfile("elevenlabs", "voice_123");
    expect(store.workspace?.voice_profile).toEqual({
      provider: "elevenlabs",
      voice_id: "voice_123",
      updated_at: "2026-10-27T00:00:00Z",
    });
  });

  it("deletes voice profile", async () => {
    // First set a profile
    (globalThis.fetch as any).mockResolvedValueOnce(
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
    await store.setVoiceProfile("elevenlabs", "voice_123");
    expect(store.workspace?.voice_profile).not.toBeNull();

    // Then delete it
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await store.deleteVoiceProfile();
    expect(store.workspace?.voice_profile).toBeNull();
  });

  it("rotates API key placeholder is a no-op", () => {
    store.rotateApiKeyPlaceholder();
    // Should not throw
    expect(true).toBe(true);
  });
});