/**
 * Application-wide Zustand store singletons.
 *
 * Pages import these singletons; tests use the `create*Store` factories from
 * the individual modules when they need an isolated instance.
 */
import { createAuthStore } from "./authStore";
import { createJobStore } from "./jobStore";
import { createProfileStore } from "./profileStore";
import { createThemeStore } from "./themeStore";

export const authStore = createAuthStore();
export const jobStore = createJobStore();
export const profileStore = createProfileStore();
export const themeStore = createThemeStore();

export type { AuthState } from "./authStore";
export type { JobStore } from "./jobStore";
export type { ProfileStore } from "./profileStore";
export type { Theme, ThemeStore } from "./themeStore";
