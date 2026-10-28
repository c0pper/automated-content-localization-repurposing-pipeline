import { useState } from "react";
import { authStore } from "@/store";
import { useTranslation } from "@/lib/useTranslation";

export interface NavProps {
  path: string;
  onNavigate: (to: string) => void;
}

export function Nav({ path, onNavigate }: NavProps) {
  const t = useTranslation();
  const [locale, setLocale] = useState<"en" | "es" | "de">("en");
  const locales = [
    { code: "en" as const, label: "EN" },
    { code: "es" as const, label: "ES" },
    { code: "de" as const, label: "DE" },
  ];

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
        <div className="flex gap-1">
          {locales.map((l) => (
            <button
              key={l.code}
              onClick={() => setLocale(l.code)}
              className={`text-xs px-2 py-1 rounded ${locale === l.code ? "bg-accent/15 text-accent" : "text-text-dim"}`}
            >
              {l.label}
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