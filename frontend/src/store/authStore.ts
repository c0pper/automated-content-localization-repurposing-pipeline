/**
 * Zustand auth slice for JWT cookie auth (issue #20).
 *
 * Keeps a minimal `user` object and manages auth state from cookie presence.
 * Navigation uses `/api/auth/login` (sets cookies), `/api/auth/logout` (clears).
 */
import { createStore } from "zustand";

export type AuthState = {
  user: { sub: string } | null;
  isAuthenticated: () => boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

export const createAuthStore = () =>
  createStore<AuthState>((set, get) => ({
    user: null,
    isAuthenticated: () => !!get().user,
    login: async () => {
      const res = await fetch("/api/auth/login", { method: "POST", credentials: "include" });
      const payload = await res.json();
      const ok = payload.detail?.code === "ok" || res.ok;
      if (ok) {
        set({ user: { sub: "creator" } });
      } else {
        throw new Error(payload.detail?.message ?? payload.message ?? "Login failed");
      }
    },
    logout: async () => {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
      set({ user: null });
    },
    refresh: async () => {
      const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
      if (!res.ok) {
        set({ user: null });
        throw new Error("Refresh failed");
      }
    },
  }));
