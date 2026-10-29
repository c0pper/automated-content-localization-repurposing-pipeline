/**
 * Localization domain (issue #40): the Creator's UI language (US14–15).
 *
 * The choice is persisted in localStorage and drives `useTranslation`, whose
 * `t.locale` every locale-aware date, duration and money format reads.
 */
import { createStore } from "zustand";
import { persist } from "zustand/middleware";
import { DICTS, type Locale } from "@/lib/i18n";

export const DEFAULT_UI_LANGUAGE: Locale = "en";

export type LocalizationStore = {
  uiLanguage: Locale;
  /** Select the UI language; languages without a string table are ignored. */
  setUILanguage: (language: string) => void;
};

const isUILanguage = (value: unknown): value is Locale =>
  typeof value === "string" && Object.hasOwn(DICTS, value);

/** Tag the document so assistive tech and the browser read it in `language`. */
function applyLanguage(language: Locale): void {
  if (typeof document !== "undefined") document.documentElement.lang = language;
}

export const createLocalizationStore = () => {
  const store = createStore<LocalizationStore>()(
    persist(
      (set) => ({
        uiLanguage: DEFAULT_UI_LANGUAGE,
        setUILanguage: (language) => {
          if (isUILanguage(language)) set({ uiLanguage: language });
        },
      }),
      {
        name: "creator-localization-storage",
        version: 1,
        partialize: (s) => ({ uiLanguage: s.uiLanguage }),
        merge: (persisted, current) => {
          const p = (persisted ?? {}) as { uiLanguage?: unknown };
          return { ...current, uiLanguage: isUILanguage(p.uiLanguage) ? p.uiLanguage : current.uiLanguage };
        },
      },
    ),
  );

  applyLanguage(store.getState().uiLanguage);
  store.subscribe((s, prev) => {
    if (s.uiLanguage !== prev.uiLanguage) applyLanguage(s.uiLanguage);
  });
  return store;
};
