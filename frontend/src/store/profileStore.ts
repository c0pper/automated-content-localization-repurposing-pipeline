/**
 * Workspace/Profile store for GET /api/workspace and Voice Profile (issue #22).
 */
import { createStore } from "zustand";
import { api } from "@/lib/api";
import type { WorkspaceSettings } from "@/lib/types";

/** Fields accepted by `PUT /api/workspace`. */
export type WorkspaceUpdate = Pick<
  WorkspaceSettings,
  | "target_language_allowlist"
  | "default_models"
  | "job_budget_usd"
  | "monthly_budget_usd"
  | "max_concurrent_jobs"
>;

export type ProfileStore = {
  workspace: WorkspaceSettings | null;
  loading: boolean;
  error: string | null;
  /** Translation key for a transient success/placeholder message. */
  notice: string | null;
  loadWorkspace: () => Promise<void>;
  updateWorkspace: (payload: WorkspaceUpdate) => Promise<void>;
  setVoiceProfile: (provider: string, voiceId: string) => Promise<void>;
  deleteVoiceProfile: () => Promise<void>;
  rotateApiKeyPlaceholder: () => void;
  clearApiKeyPlaceholder: () => void;
  clearNotice: () => void;
};

function messageOf(e: unknown): string {
  return e instanceof Error && e.message ? e.message : String(e);
}

export const createProfileStore = () =>
  createStore<ProfileStore>((set) => ({
    workspace: null,
    loading: false,
    error: null,
    notice: null,

    loadWorkspace: async () => {
      set({ loading: true, error: null });
      try {
        const workspace = await api.get<WorkspaceSettings>("/workspace");
        set({ workspace, loading: false });
      } catch (e) {
        set({ loading: false, error: messageOf(e) });
        throw e;
      }
    },

    updateWorkspace: async (payload) => {
      set({ loading: true, error: null });
      try {
        const workspace = await api.put<WorkspaceSettings>("/workspace", payload);
        set({ workspace, loading: false });
      } catch (e) {
        set({ loading: false, error: messageOf(e) });
        throw e;
      }
    },

    setVoiceProfile: async (provider, voiceId) => {
      set({ loading: true, error: null, notice: null });
      try {
        const res = await api.put<{
          voice_profile: WorkspaceSettings["voice_profile"];
        }>("/workspace/voice-profile", { provider, voice_id: voiceId });
        const updated = res.voice_profile;
        set((state) => ({
          workspace: state.workspace
            ? { ...state.workspace, voice_profile: updated }
            : state.workspace,
          loading: false,
          notice: "voiceProfileUpdated",
        }));
      } catch (e) {
        set({ loading: false, error: messageOf(e) });
        throw e;
      }
    },

    deleteVoiceProfile: async () => {
      set({ loading: true, error: null, notice: null });
      try {
        await api.delete("/workspace/voice-profile");
        set((state) => ({
          workspace: state.workspace
            ? { ...state.workspace, voice_profile: null }
            : state.workspace,
          loading: false,
          notice: "voiceProfileDeleted",
        }));
      } catch (e) {
        set({ loading: false, error: messageOf(e) });
        throw e;
      }
    },

    rotateApiKeyPlaceholder: () => {
      set({ notice: "apiKeyRotationPlaceholder" });
    },

    clearApiKeyPlaceholder: () => {
      set({ notice: "apiKeyClearPlaceholderMessage" });
    },

    clearNotice: () => {
      set({ notice: null });
    },
  }));
