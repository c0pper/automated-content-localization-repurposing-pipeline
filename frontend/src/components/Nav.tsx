import { useStore } from "zustand";
import { authStore, localizationStore } from "@/store";
import { useTranslation } from "@/lib/useTranslation";
import { UI_LANGUAGES, type Locale } from "@/lib/i18n";

export interface NavProps {
  path: string;
  onNavigate: (to: string) => void;
}

/** Each UI language named in itself, so a Creator can find theirs from any UI language. */
const LANGUAGE_NAMES: Record<Locale, string> = {
  en: "English",
  es: "Español",
  de: "Deutsch",
};

export function Nav({ path, onNavigate }: NavProps) {
  const t = useTranslation();
  const uiLanguage = useStore(localizationStore, (s) => s.uiLanguage);

  const linkCls = (to: string) =>
    `px-3 py-2 rounded-lg transition ${
      path === to || (to === "/dashboard" && !path.startsWith("/dashboard/"))
        ? "bg-accent/15 text-accent"
        : "text-text-dim hover:text-text hover:bg-surface-2"
    }`;

  const logout = async () => {
    await authStore.getState().logout();
  };

  return (
    <nav className="flex items-center justify-between gap-4 bg-surface border-b border-border sticky top-0 z-10 w-full px-4 py-2">
      <div className="flex items-center gap-1 min-w-0">
        <button
          onClick={() => onNavigate("/dashboard")}
          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-2 transition"
          aria-label="Go to dashboard"
        >
          <svg className="h-5 w-5 text-accent" viewBox="0 0 24 24" fill="currentColor" focusable="false">
            <path d="M10 6L8.59 9.14 14.15 15H10V6ZM14 4l-4 4 4 4H8L6 8l6 4 2-4h-2V4h8Z" />
          </svg>
          <span className="text-sm text-text-dim hidden sm:inline">{t.dashboard}</span>
        </button>
        <button
          onClick={() => onNavigate("/jobs")}
          className={linkCls("/jobs")}
          aria-label={t.jobs}
        >
          {t.jobs}
        </button>
        <button
          onClick={() => onNavigate("/jobs/new")}
          className={linkCls("/jobs/new")}
          aria-label={t.newJob}
        >
          {t.newJob}
        </button>
        <button
          onClick={() => onNavigate("/profile")}
          className={linkCls("/profile")}
          aria-label={t.profile}
        >
          {t.profile}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex gap-1" role="group" aria-label={t.language}>
          {UI_LANGUAGES.map((code) => (
            <button
              key={code}
              type="button"
              lang={code}
              aria-label={LANGUAGE_NAMES[code]}
              aria-pressed={uiLanguage === code}
              onClick={() => localizationStore.getState().setUILanguage(code)}
              className={`text-xs px-2 py-1 rounded ${uiLanguage === code ? "bg-accent/15 text-accent" : "text-text-dim"}`}
            >
              {code.toUpperCase()}
            </button>
          ))}
        </div>
        <button
          onClick={logout}
          className="text-sm text-red-400 hover:text-red-300 transition px-3 py-2 rounded-lg"
          aria-label={t.logout}
        >
          {t.logout}
        </button>
      </div>
    </nav>
  );
}