/**
 * Workspace/Profile store for GET /api/workspace and Voice Profile (issue #22).
 */
import { createStore } from "zustand";
import { api } from "@/lib/api";
import type { WorkspaceSettings } from "@/lib/types";

export type ProfileStore = {
  workspace: WorkspaceSettings | null;
  loading: boolean;
  error: string | null;
  loadWorkspace: () => Promise<void>;
  updateWorkspace: (payload: Partial<WorkspaceSettings>) => Promise<void>;
  setVoiceProfile: (provider: string, voiceId: string) => Promise<void>;
  deleteVoiceProfile: () => Promise<void>;
  rotateApiKeyPlaceholder: () => void;
  clearApiKeyPlaceholder: () => void;
};

export const createProfileStore = () =>
  createStore<ProfileStore>((set) => ({
    workspace: null,
    loading: false,
    error: null,
    loadWorkspace: async () => {
      set({ loading: true, error: null });
      try {
        const workspace = await api.get<WorkspaceSettings>("/workspace");
        set({ workspace, loading: false });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        set({ loading: false, error: msg });
        throw e;
      }
    },
    updateWorkspace: async (payload) => {
      set({ loading: true, error: null });
      try {
        const workspace = await api.put<WorkspaceSettings>("/workspace", payload);
        set({ workspace, loading: false });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        set({ loading: false, error: msg });
        throw e;
      }
    },
    setVoiceProfile: async (provider, voiceId) => {
      set({ loading: true, error: null });
      try {
        const res = await api.put<{ voice_profile: WorkspaceSettings["voice_profile"] }>(
          "/workspace/voice-profile",
          { provider, voice_id: voiceId },
        );
        set((state) => ({
          workspace: state.workspace
            ? {
                ...state.workspace,
                voice_profile: updated
                  ? { provider: updated.provider, voice_id: updated.voice_id, updated_at: updated.updated_at }
                  : null,
              }
            : null,
          loading: false,
        }));
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        set({ loading: false, error: msg });
        throw e;
      }
    },
    deleteVoiceProfile: async () => {
      set({ loading: true, error: null });
      try {
        await api.delete("/workspace/voice-profile");
        set((state) => ({
          workspace: state.workspace ? { ...state.workspace, voice_profile: null } : null,
          loading: false,
        }));
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        set({ loading: false, error: msg });
        throw e;
      }
    },
    rotateApiKeyPlaceholder: () => {
      set({ error: "API key rotation is a placeholder in v1 — manage externally." });
    },
    clearApiKeyPlaceholder: () => {
      set({ error: "API key cleared (placeholder) — regenerate externally." });
    },
  }));