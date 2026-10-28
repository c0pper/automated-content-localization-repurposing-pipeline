/**
 * UI theme domain (issue #23): black background + selectable neon accent.
 *
 * The selected accent is persisted in localStorage and written to CSS
 * variables on <html>, which Tailwind's `accent*` colors read, so a change
 * applies instantly across every page.
 */
import { createStore } from "zustand";
import { devtools, persist } from "zustand/middleware";
import { hexToRgb } from "@/lib/contrast";

/** App background (`--bg`); every accent is validated against it. */
export const BACKGROUND = "#050505";

export type Theme = {
  name: string;
  accent: string;
  /** Text color used on top of an accent-filled surface. */
  contrast: string;
};

export const THEMES: Theme[] = [
  { name: "cyan", accent: "#00ffff", contrast: "#000000" },
  { name: "green", accent: "#00ff00", contrast: "#000000" },
  { name: "magenta", accent: "#ff00ff", contrast: "#000000" },
  { name: "amber", accent: "#ffbf00", contrast: "#000000" },
];

export const DEFAULT_THEME = THEMES[0];

export type ThemeStore = {
  theme: Theme;
  accent: string;
  isDark: boolean;
  /** Select an accent by name; unknown names are ignored. */
  setAccentColor: (name: string) => void;
  /** Alias of `setAccentColor`. */
  setTheme: (name: string) => void;
  toggleDarkMode: () => void;
};

const findTheme = (name: unknown) => THEMES.find((t) => t.name === name);

/** Write the theme's CSS variables onto the document root. */
export function applyTheme(theme: Theme, isDark = true, root?: HTMLElement): void {
  const el = root ?? (typeof document !== "undefined" ? document.documentElement : undefined);
  if (!el) return;
  const rgb = hexToRgb(theme.accent).join(" ");
  el.style.setProperty("--accent", theme.accent);
  el.style.setProperty("--accent-rgb", rgb);
  el.style.setProperty("--accent-soft", `rgb(${rgb} / 0.12)`);
  el.style.setProperty("--accent-contrast", theme.contrast);
  el.dataset.accent = theme.name;
  el.classList.toggle("dark", isDark);
}

export const createThemeStore = () => {
  const store = createStore<ThemeStore>()(
    devtools(
      persist(
        (set, get) => {
          const select = (name: string) => {
            const theme = findTheme(name);
            if (!theme || theme === get().theme) return;
            set({ theme, accent: theme.accent });
          };
          return {
            theme: DEFAULT_THEME,
            accent: DEFAULT_THEME.accent,
            isDark: true,
            setAccentColor: select,
            setTheme: select,
            toggleDarkMode: () => set((s) => ({ isDark: !s.isDark })),
          };
        },
        {
          name: "creator-theme-storage",
          version: 1,
          partialize: (s) => ({ themeName: s.theme.name, isDark: s.isDark }),
          merge: (persisted, current) => {
            const p = (persisted ?? {}) as { themeName?: unknown; isDark?: unknown };
            const theme = findTheme(p.themeName) ?? current.theme;
            return {
              ...current,
              theme,
              accent: theme.accent,
              isDark: typeof p.isDark === "boolean" ? p.isDark : current.isDark,
            };
          },
          migrate: (persisted) => {
            // v0 stored the whole Theme object.
            const p = (persisted ?? {}) as { theme?: { name?: string }; isDark?: boolean };
            return { themeName: p.theme?.name, isDark: p.isDark };
          },
        },
      ),
      { name: "theme-store", enabled: import.meta.env?.DEV ?? false },
    ),
  );

  applyTheme(store.getState().theme, store.getState().isDark);
  store.subscribe((s, prev) => {
    if (s.theme !== prev.theme || s.isDark !== prev.isDark) applyTheme(s.theme, s.isDark);
  });
  return store;
};
