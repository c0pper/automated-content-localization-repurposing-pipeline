import { createStore } from "zustand";
import { persist } from "zustand/middleware";
import { devtools } from "zustand/middleware";

export type Theme = { name: string; accent: string };

export const THEMES: Theme[] = [
  { name: "cyan", accent: "#00ffff" },
  { name: "green", accent: "#00ff00" },
  { name: "magenta", accent: "#ff00ff" },
  { name: "amber", accent: "#ffbf00" },
];

export type ThemeStore = {
  theme: Theme;
  accent: string;
  setTheme: (name: string) => void;
  isDark: boolean;
  toggleDarkMode: () => void;
};

export const createThemeStore = () =>
  createStore<ThemeStore>()(
    devtools(
      persist(
        (set) => ({
          theme: THEMES[0],
          accent: THEMES[0].accent,
          isDark: true,
          setTheme: (name) => {
            const theme = THEMES.find((t) => t.name === name) ?? THEMES[0];
            set({ theme, accent: theme.accent });
          },
          toggleDarkMode: () =>
            set((state) => ({ isDark: !state.isDark })),
        }),
        { name: "creator-theme-storage" },
      ),
      { name: "theme-store" },
    ),
  );