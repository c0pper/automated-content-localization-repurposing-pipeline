/** Accent color picker (issue #23): an accessible radio group of neon swatches. */
import { useRef, type KeyboardEvent } from "react";
import { useStore } from "zustand";
import { useTranslation } from "@/lib/useTranslation";
import { themeStore } from "@/store";
import { THEMES } from "@/store/themeStore";

const LABEL_KEYS: Record<string, string> = {
  cyan: "accentCyan",
  green: "accentGreen",
  magenta: "accentMagenta",
  amber: "accentAmber",
};

export function ThemeSelector() {
  const t = useTranslation();
  const current = useStore(themeStore, (s) => s.theme.name);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const select = (index: number) => {
    const theme = THEMES[(index + THEMES.length) % THEMES.length];
    themeStore.getState().setAccentColor(theme.name);
    refs.current[THEMES.indexOf(theme)]?.focus();
  };

  const onKeyDown = (e: KeyboardEvent, index: number) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      select(index + 1);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      select(index - 1);
    }
  };

  return (
    <section className="bg-surface rounded-xl border border-border p-6 space-y-3" aria-labelledby="accent-color-heading">
      <h3 id="accent-color-heading" className="font-semibold">{t.accentColor}</h3>
      <p id="accent-color-hint" className="text-sm text-text-dim">{t.accentColorHint}</p>
      <div
        role="radiogroup"
        aria-labelledby="accent-color-heading"
        aria-describedby="accent-color-hint"
        className="flex flex-wrap gap-3"
      >
        {THEMES.map((theme, i) => {
          const checked = theme.name === current;
          const label = t[LABEL_KEYS[theme.name]] ?? theme.name;
          return (
            <button
              key={theme.name}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-label={label}
              tabIndex={checked ? 0 : -1}
              onClick={() => select(i)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`flex min-h-11 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
                checked ? "border-accent text-text" : "border-border text-text-dim hover:text-text"
              }`}
            >
              <span
                aria-hidden="true"
                className="h-5 w-5 rounded-full border border-border"
                style={{ backgroundColor: theme.accent, boxShadow: checked ? `0 0 0 2px ${theme.accent}55` : undefined }}
              />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
